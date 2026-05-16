"""
core/agent_bridge.py
Bridges UI events to the agent system.
- Caches a single agents() instance
- Runs autonomous_tick() at an interval configured in core.config
- Polls Minecraft context for item changes
- Adapts poll frequency based on whether Minecraft is running
"""
import threading
import queue
import time
from typing import Optional, Callable
from .short_memory import ShortTermMemory
from .messaging import RandomMessenger

try:
    from core import config as _cfg
    _AUTONOMOUS_INTERVAL = _cfg.AUTONOMOUS_INTERVAL_DEFAULT
except Exception:
    _AUTONOMOUS_INTERVAL = 30   # seconds between autonomous behaviour ticks


class AgentBridge:
    def __init__(
            self,
            ui_show_callback: Optional[Callable[[str], None]] = None,
            messenger_interval: int = 30,
            memory_max_items: int = 200,
            mc_bridge=None,
    ):
        # Apply config-level memory cap if config is available
        try:
            from core.config import SHORT_MEMORY_MAX_ITEMS
            memory_max_items = min(memory_max_items, SHORT_MEMORY_MAX_ITEMS)
        except Exception:
            pass

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

        # Track MC detection state so we can adapt poll intervals
        self._mc_detected: bool = False
        self._last_mc_detect: float = 0.0

        self._worker_thread.start()
        self.messenger.start()

        # Track last held item for change detection
        self._last_held_item = None

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
        last_mc_poll      = time.time()
        last_auto_tick    = time.time()
        last_context_check = time.time()

        # Load config values (with safe fallbacks)
        try:
            from core import config as _cfg
            _poll_mc      = _cfg.POLL_INTERVAL_MINECRAFT   # 2 s
            _poll_idle    = _cfg.POLL_INTERVAL_IDLE         # 10 s
            _mc_detect    = _cfg.MC_DETECT_INTERVAL         # 15 s
            _auto_mc      = _cfg.AUTONOMOUS_INTERVAL_MINECRAFT
            _auto_default = _cfg.AUTONOMOUS_INTERVAL_DEFAULT
        except Exception:
            _poll_mc      = 2.0
            _poll_idle    = 10.0
            _mc_detect    = 15.0
            _auto_mc      = 15.0
            _auto_default = 30.0

        while not self._stop_event.is_set():
            now = time.time()
            mc_chat_interval = _poll_mc if self._mc_detected else _poll_idle
            ctx_interval = _poll_mc if (self._mc_detected or self._mc_bridge) else _poll_idle
            auto_interval = _auto_mc if self._mc_detected else _auto_default
            next_timeout = min(
                max(0.25, _mc_detect - (now - self._last_mc_detect)),
                max(0.25, mc_chat_interval - (now - last_mc_poll)),
                max(0.25, ctx_interval - (now - last_context_check)),
                max(0.25, auto_interval - (now - last_auto_tick)),
                2.0,
            )
            try:
                item = self._q.get(timeout=next_timeout)
            except queue.Empty:
                now = time.time()

                # ── Periodic MC process detection (cheap psutil scan) ──────
                if now - self._last_mc_detect > _mc_detect:
                    self._last_mc_detect = now
                    try:
                        from core.platform_utils import is_minecraft_running
                        self._mc_detected = is_minecraft_running()
                    except Exception:
                        pass

                # ── Poll Minecraft chat ───────────────────────────────────
                # Slow down when Minecraft is not detected to save CPU.
                if now - last_mc_poll > mc_chat_interval:
                    last_mc_poll = now
                    if self._agents_instance:
                        try:
                            self._agents_instance.poll_minecraft_chat()
                        except Exception:
                            pass

                # ── Check Minecraft context for held-item changes ─────────
                # Only run when MC is detected or bridge is active.
                if now - last_context_check > ctx_interval:
                    last_context_check = now
                    if self._agents_instance and self._mc_bridge:
                        try:
                            self._check_held_item_change()
                        except Exception as e:
                            print(f"Context check error: {e}")

                # ── Autonomous behaviour tick ─────────────────────────────
                # Use shorter interval while MC is active.
                if now - last_auto_tick > auto_interval:
                    last_auto_tick = now
                    if self._agents_instance:
                        try:
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

    def _check_held_item_change(self):
        """Check Minecraft context for held item changes and notify agent."""
        if not self._mc_bridge:
            return

        context = self._mc_bridge.get_context()
        if not context:
            return

        held_item = context.get("held_main", "empty")

        # Only notify agent if item changed
        if held_item != self._last_held_item:
            self._last_held_item = held_item

            # Emit MINECRAFT_CONTEXT event to agents
            if self._agents_instance:
                try:
                    self._agents_instance.handle({
                        "type": "MINECRAFT_CONTEXT",
                        "held_item": held_item
                    })
                except Exception as e:
                    print(f"Error handling context event: {e}")

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
