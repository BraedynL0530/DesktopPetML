# core/agent_bridge.py
"""
Optimized AgentBridge:
- processes incoming events on a single worker thread (queue) to avoid blocking UI
- stores events into short-term memory, forwards to agents.handle(...)
- provides a thread-safe pathway for messenger -> UI by calling a user-supplied show_callback
- clean lifecycle: start/stop join for threads
"""
import threading
import queue
import time
from typing import Optional, Callable
from .short_memory import ShortTermMemory
from .messaging import RandomMessenger

try:
    from .agents import agents as AgentsClass
except Exception:
    # fallback import path - if your code layout differs adjust accordingly
    from core.agents import agents as AgentsClass


class AgentBridge:
    def __init__(
        self,
        ui_show_callback: Optional[Callable[[str], None]] = None,
        messenger_interval: int = 30,
        memory_max_items: int = 500,
    ):
        """
        ui_show_callback(text) should be a thread-safe callable (e.g. a Qt-slot-wrapper that emits a signal).
        If it's not thread-safe, ensure you pass a wrapper that marshals to the UI thread.
        """
        self.ui_show_callback = ui_show_callback
        self.agents = AgentsClass()
        self.memory = ShortTermMemory(max_items=memory_max_items)

        # event queue for worker thread
        self._q = queue.Queue(maxsize=200)
        self._worker_thread = threading.Thread(target=self._worker_loop, name="AgentBridgeWorker", daemon=True)
        self._stop_event = threading.Event()

        # messenger sends pet messages; use show_callback that routes via the queue for consistent ordering
        # messenger should make short calls only; we'll route any UI display through self._emit_show so it remains ordered.
        self.messenger = RandomMessenger(show_callback=self._emit_show, memory=self.memory, interval=messenger_interval)

        self._worker_thread.start()
        self.messenger.start()

    # internal: route messenger text into the worker queue to preserve ordering
    def _emit_show(self, text: str):
        # place a special 'SHOW' message into the queue; worker will call ui_show_callback on main thread wrapper
        try:
            self._q.put_nowait({"type": "_SHOW", "text": text})
        except queue.Full:
            # if queue is full, drop the message (messenger will try again later)
            pass

    def handle(self, event: dict):
        """
        Public API for UI to send events to the agent pipeline.
        This returns quickly (non-blocking) and puts the event in the processing queue.
        event examples:
          {"type":"STT_COMMAND", "text": "..."}
          {"type":"VISION_SNAPSHOT", "path": "...", "source": "..."}
        """
        try:
            self._q.put_nowait({"type": "EVENT", "event": event})
        except queue.Full:
            # queue full - drop oldest event to make room, then push (best-effort)
            try:
                _ = self._q.get_nowait()
                self._q.put_nowait({"type": "EVENT", "event": event})
            except Exception:
                # if even that fails, swallow the event to keep UI responsive
                pass

    def _worker_loop(self):
        while not self._stop_event.is_set():
            try:
                item = self._q.get(timeout=0.5)
            except Exception:
                continue

            try:
                if item["type"] == "_SHOW":
                    # deliver text to UI via supplied callback (should be thread-safe)
                    if callable(self.ui_show_callback):
                        try:
                            self.ui_show_callback(item["text"])
                        except Exception:
                            # UI callback failed; ignore to avoid killing worker
                            pass

                elif item["type"] == "EVENT":
                    ev = item["event"]
                    # store into short-term memory for context (best-effort; adapt to your memory schema)
                    try:
                        etype = ev.get("type")
                        if etype == "STT_COMMAND":
                            txt = ev.get("text", "")
                            self.memory.add_chat(txt, who="user")
                        elif etype == "VISION_SNAPSHOT":
                            # agents.vision may produce summary itself; we store a placeholder path event now
                            self.memory.add("vision_event", {"path": ev.get("path"), "source": ev.get("source")})
                    except Exception:
                        # memory write error - continue
                        pass

                    # forward to agents for LLM/vision/intent processing
                    try:
                        self.agents.handle(ev)
                    except Exception:
                        # do not propagate exceptions to worker loop; log if you add logging
                        pass

                # done with item
            finally:
                try:
                    self._q.task_done()
                except Exception:
                    pass

        # exiting loop; optionally flush anything or perform cleanup

    def get_context_summary(self, max_items=10) -> str:
        return self.memory.get_context_summary(max_items=max_items)

    def stop(self, wait: bool = True, timeout: Optional[float] = 5.0):
        """
        Stop the bridge and its background threads.
        - wait: if True will join worker and stop messenger
        - timeout: maximum seconds to join worker thread
        """
        self._stop_event.set()

        # stop messenger and give it a moment
        try:
            self.messenger.stop()
        except Exception:
            pass

        # wake worker by putting a dummy item if it's waiting
        try:
            self._q.put_nowait({"type": "_WAKE"})
        except Exception:
            pass

        if wait:
            # join messenger thread (it is a daemon thread in the messaging implementation)
            # join worker thread
            start = time.time()
            while self._worker_thread.is_alive():
                self._worker_thread.join(timeout=0.2)
                if timeout is not None and (time.time() - start) > timeout:
                    break

    # convenience: helper to immediately show a line on UI (routes through queue for ordering)
    def show_now(self, text: str):
        self._emit_show(text)