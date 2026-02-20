"""
core/agent_bridge.py
Bridges UI events to the agent system.
Now caches a single agents() instance (instead of recreating each event)
and passes the minecraft bridge through so MinecraftAgent is initialized.
"""
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
            mc_bridge=None,          # ← pass MinecraftBridge instance here
    ):
        self.ui_show_callback = ui_show_callback
        self.memory = ShortTermMemory(max_items=memory_max_items)
        self._mc_bridge = mc_bridge

        # ── Cache a single agents instance so it keeps its minecraft_agent ─
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
        """Create agents instance once, passing the mc_bridge."""
        try:
            from core.agents import agents
            self._agents_instance = agents(mc_bridge=self._mc_bridge)
            print("✓ agents initialized" + (" with Minecraft bridge" if self._mc_bridge else ""))
        except Exception as e:
            print(f"⚠ agents init failed: {e}")
            self._agents_instance = None

    def set_mc_bridge(self, mc_bridge):
        """
        Attach a Minecraft bridge after construction
        (called from pet.py once the bridge thread confirms it started).
        """
        self._mc_bridge = mc_bridge
        self._init_agents()   # reinit with bridge

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
        last_mc_poll = time.time()

        while not self._stop_event.is_set():
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                # Poll Minecraft chat every second even when queue is idle
                if time.time() - last_mc_poll > 1.0:
                    last_mc_poll = time.time()
                    if self._agents_instance:
                        try:
                            self._agents_instance.poll_minecraft_chat()
                        except Exception:
                            pass
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
                    ev = item.get("event", {})
                    etype = ev.get("type")

                    # Store in memory
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

                    # Forward to cached agents instance
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