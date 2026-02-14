import threading
import queue
import time
from typing import Optional, Callable
from .short_memory import ShortTermMemory
from .messaging import RandomMessenger  # or from core.messaging if that's your filename

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

        # Correct: Pass the memory object directly!
        self.messenger = RandomMessenger(
            show_callback=self._emit_show,
            memory=self.memory,
            interval=messenger_interval
        )

        self._worker_thread.start()
        self.messenger.start()

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
                _ = self._q.get_nowait()
                self._q.put_nowait({"type": "EVENT", "event": event})
            except Exception:
                pass

    def _worker_loop(self):
        while not self._stop_event.is_set():
            try:
                item = self._q.get(timeout=0.5)
            except Exception:
                continue
            # ...handle events...

    def stop(self, wait=False, timeout=5.0):
        self._stop_event.set()
        if wait and self._worker_thread.is_alive():
            self._worker_thread.join(timeout)
        self.messenger.stop()