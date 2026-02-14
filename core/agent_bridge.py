import threading
import queue
import time
from typing import Optional, Callable
from .short_memory import ShortTermMemory
from .messaging import RandomMessenger


class AgentBridge:
    def __init__(
            self,
            ui_show_callback: Optional[Callable[[str], None]] = None,
            messenger_interval: int = 30,
            memory_max_items: int = 500,
    ):
        self.ui_show_callback = ui_show_callback
        self.memory = ShortTermMemory(max_items=memory_max_items)

        # Queue for events
        self._q = queue.Queue(maxsize=200)
        self._worker_thread = threading.Thread(target=self._worker_loop, name="AgentBridgeWorker", daemon=True)
        self._stop_event = threading.Event()

        # Pass memory object directly
        self.messenger = RandomMessenger(
            show_callback=self._emit_show,
            memory=self.memory,
            interval=messenger_interval
        )

        self._worker_thread.start()
        self.messenger.start()

    def _emit_show(self, text: str):
        """Put show request in queue"""
        try:
            self._q.put_nowait({"type": "_SHOW", "text": text})
        except queue.Full:
            pass

    def handle(self, event: dict):
        """Handle events from UI (STT, etc)"""
        try:
            self._q.put_nowait({"type": "EVENT", "event": event})
        except queue.Full:
            try:
                _ = self._q.get_nowait()
                self._q.put_nowait({"type": "EVENT", "event": event})
            except Exception:
                pass

    def _worker_loop(self):
        """Main worker loop - FIXED VERSION"""
        print("🔧 AgentBridge worker loop started")

        while not self._stop_event.is_set():
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Queue get error: {e}")
                continue

            try:
                # Handle _SHOW messages from messenger
                if item.get("type") == "_SHOW":
                    text = item.get("text", "")
                    print(f"🔧 Worker processing SHOW: {text}")

                    if callable(self.ui_show_callback):
                        try:
                            self.ui_show_callback(text)  # This should emit the signal
                            print(f"✅ Callback executed for: {text}")
                        except Exception as e:
                            print(f"❌ Callback failed: {e}")
                            import traceback
                            traceback.print_exc()

                # Handle EVENT messages (STT commands, etc)
                elif item.get("type") == "EVENT":
                    ev = item.get("event", {})
                    print(f"🔧 Worker processing EVENT: {ev.get('type')}")

                    # Store in memory
                    try:
                        etype = ev.get("type")
                        if etype == "STT_COMMAND":
                            txt = ev.get("text", "")
                            self.memory.add_chat(txt, who="user")
                        elif etype == "VISION_SNAPSHOT":
                            self.memory.add("vision_event", {
                                "path": ev.get("path"),
                                "source": ev.get("source")
                            })
                    except Exception as e:
                        print(f"Memory write error: {e}")

                    # Forward to agents
                    try:
                        from core.agents import agents
                        agent_instance = agents()
                        agent_instance.handle(ev)
                    except Exception as e:
                        print(f"Agent handling error: {e}")

            except Exception as e:
                print(f"Worker loop error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                try:
                    self._q.task_done()
                except Exception:
                    pass

        print("🔧 AgentBridge worker loop stopped")

    def get_context_summary(self, max_items=10) -> str:
        """Get context summary from memory"""
        return self.memory.get_context_summary(max_items=max_items)

    def stop(self, wait=False, timeout=5.0):
        """Stop the bridge and background threads"""
        print("🛑 Stopping AgentBridge...")
        self._stop_event.set()

        # Stop messenger
        try:
            self.messenger.stop()
        except Exception as e:
            print(f"Error stopping messenger: {e}")

        # Wake worker
        try:
            self._q.put_nowait({"type": "_WAKE"})
        except Exception:
            pass

        if wait and self._worker_thread.is_alive():
            self._worker_thread.join(timeout)

    def show_now(self, text: str):
        """Immediately show text (routes through queue for ordering)"""
        self._emit_show(text)