"""
core/agent_bridge.py
Bridges UI events to the agent system.
- Caches a single agents() instance
- Runs autonomous_tick() every 30s when Minecraft is active
"""
import threading
import queue
import time
from typing import Optional, Callable
from .short_memory import ShortTermMemory
from .messaging import RandomMessenger

_AUTONOMOUS_INTERVAL = 10   # seconds between autonomous behaviour ticks
#found working commit

class AgentBridge:
    def __init__(
            self,
            ui_show_callback: Optional[Callable[[str], None]] = None,
            messenger_interval: int = 30,
            memory_max_items: int = 500,
            mc_bridge=None,
    ):
        self.ui_show_callback = ui_show_callback
        self.memory = ShortTermMemory(max_items=memory_max_items)
        self._mc_bridge = mc_bridge

        self._agents_instance = None
        self._init_agents()

        self._q = queue.Queue(maxsize=200)
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="AgentBridgeWorker", daemon=True)
        self._stop_event = threading.Event()

        self.messenger = RandomMessenger(
            show_callback=self._emit_show,
            memory=self.memory,
            interval=messenger_interval
        )

        self._worker_thread.start()
        self.messenger.start()

    def _init_agents(self):
        try:
            from core.agents import agents
            self._agents_instance = agents(mc_bridge=self._mc_bridge)
            print("✓ agents initialized" + (" with Minecraft bridge" if self._mc_bridge else ""))
        except Exception as e:
            print(f"⚠ agents init failed: {e}")
            self._agents_instance = None

    def set_mc_bridge(self, mc_bridge):
        self._mc_bridge = mc_bridge
        self._init_agents()

    def _emit_show(self, text: str):
        try:
            self._q.put_nowait({"type": "_SHOW", "text": text})
        except queue.Full:
            pass

    def handle(self, event: dict):
        try:
            self._q.put_nowait({"type": "EVENT", "event": event})
        except queue.Full:
            try:
                self._q.get_nowait()
                self._q.put_nowait({"type": "EVENT", "event": event})
            except Exception:
                pass

    def _worker_loop(self):
        print("🔧 AgentBridge worker loop started")
        last_mc_poll   = time.time()
        last_auto_tick = time.time()

        while not self._stop_event.is_set():
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                now = time.time()

                # Poll Minecraft chat every second
                if now - last_mc_poll > 1.0:
                    last_mc_poll = now
                    if self._agents_instance:
                        try:
                            self._agents_instance.poll_minecraft_chat()
                        except Exception:
                            pass

                # Autonomous behaviour tick every 30 s while MC is active
                if now - last_auto_tick > _AUTONOMOUS_INTERVAL:
                    last_auto_tick = now
                    if self._agents_instance:
                        try:
                            # Only fire when a Minecraft bridge exists
                            if self._agents_instance.minecraft_agent:
                                self._agents_instance.autonomous_tick()
                        except Exception as e:
                            print(f"autonomous_tick error: {e}")
                continue
            except Exception as e:
                print(f"Queue get error: {e}")
                continue

            try:
                if item.get("type") == "_SHOW":
                    text = item.get("text", "")
                    if callable(self.ui_show_callback):
                        try:
                            self.ui_show_callback(text)
                        except Exception as e:
                            print(f"❌ UI callback failed: {e}")

                elif item.get("type") == "EVENT":
                    ev    = item.get("event", {})
                    etype = ev.get("type")

                    try:
                        if etype == "STT_COMMAND":
                            self.memory.add_chat(ev.get("text", ""), who="user")
                        elif etype == "VISION_SNAPSHOT":
                            self.memory.add("vision_event", {
                                "path": ev.get("path"),
                                "source": ev.get("source")
                            })
                    except Exception as e:
                        print(f"Memory write error: {e}")

                    if self._agents_instance:
                        try:
                            self._agents_instance.handle(ev)
                        except Exception as e:
                            print(f"Agent handling error: {e}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print("⚠ No agents instance available")

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
        return self.memory.get_context_summary(max_items=max_items)

    def stop(self, wait=False, timeout=5.0):
        print("🛑 Stopping AgentBridge...")
        self._stop_event.set()
        try:
            self.messenger.stop()
        except Exception as e:
            print(f"Error stopping messenger: {e}")
        try:
            self._q.put_nowait({"type": "_WAKE"})
        except Exception:
            pass
        if wait and self._worker_thread.is_alive():
            self._worker_thread.join(timeout)

    def show_now(self, text: str):
        self._emit_show(text)