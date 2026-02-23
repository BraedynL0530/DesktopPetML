"""
minecraft/minecraft_bridge.py
HTTP bridge with distance-based movement and context optimization.
Sends only changed context values (diffs) instead of full state.
"""

import json
import logging
import threading
import time
import uuid
from collections import deque
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)

_pending: deque = deque()
_results: Dict[str, Any] = {}
_results_lock = threading.Lock()
_result_events: Dict[str, threading.Event] = {}

_latest_context: Dict = {}
_context_lock = threading.Lock()
_previous_context: Dict = {}  # Track changes for diff optimization

_chat_queue: deque = deque()
_chat_lock = threading.Lock()


def _enqueue(cmd: dict) -> str:
    cmd_id = str(uuid.uuid4())[:8]
    cmd["id"] = cmd_id
    _pending.append(cmd)
    _result_events[cmd_id] = threading.Event()
    return cmd_id


def _wait_result(cmd_id: str, timeout: float = 5.0) -> Optional[Any]:
    event = _result_events.get(cmd_id)
    if event and event.wait(timeout):
        with _results_lock:
            return _results.pop(cmd_id, None)
    return None


def get_context() -> dict:
    """Get latest context snapshot."""
    with _context_lock:
        return dict(_latest_context)


def _context_diff(new_context: dict) -> dict:
    """
    Compare new context with previous and return only changed values.
    Reduces HTTP payload significantly.
    """
    global _previous_context

    diff = {}
    for key, value in new_context.items():
        if key not in _previous_context or _previous_context[key] != value:
            diff[key] = value

    _previous_context = dict(new_context)
    return diff


_app = Flask(__name__)


@_app.route("/commands", methods=["GET"])
def get_commands():
    """Scarpet polls here to fetch command queue."""
    batch = []
    for _ in range(10):
        if _pending:
            batch.append(_pending.popleft())
        else:
            break
    return jsonify(batch)


@_app.route("/results", methods=["POST"])
def post_results():
    """Scarpet posts command execution results here."""
    items = request.get_json(force=True, silent=True) or []
    if not isinstance(items, list):
        items = [items]
    with _results_lock:
        for item in items:
            if isinstance(item, list):
                try:
                    item = dict(item)
                except Exception:
                    continue
            if not isinstance(item, dict):
                continue
            cmd_id = item.get("id")
            if cmd_id and cmd_id in _result_events:
                _results[cmd_id] = item
                _result_events[cmd_id].set()
    return jsonify({"ack": len(items)})


@_app.route("/context", methods=["POST"])
def post_context():
    """Scarpet pushes world state here (only changed values)."""
    data = request.get_json(force=True, silent=True) or {}
    with _context_lock:
        # Merge diff into latest context instead of clearing
        _latest_context.update(data)
    return jsonify({"ok": True})


@_app.route("/context", methods=["GET"])
def get_context_endpoint():
    """Agent polls latest context here."""
    return jsonify(get_context())


@_app.route("/chat", methods=["POST"])
def post_chat():
    """Scarpet forwards player chat here."""
    data = request.get_json(force=True, silent=True) or {}
    with _chat_lock:
        _chat_queue.append(data)
    return jsonify({"ok": True})


@_app.route("/chat", methods=["GET"])
def get_chat():
    """Agent polls for player chat."""
    messages = []
    with _chat_lock:
        while _chat_queue:
            messages.append(_chat_queue.popleft())
    return jsonify(messages)


@_app.route("/health", methods=["GET"])
def health():
    """Health check."""
    return jsonify({"status": "ok", "pending": len(_pending)})


@_app.route("/inject", methods=["POST"])
def inject():
    """Manual test endpoint."""
    cmd = request.get_json(force=True, silent=True) or {}
    cmd_id = _enqueue(cmd)
    return jsonify({"queued": True, "id": cmd_id})


def _start_http_server(host: str, port: int):
    import werkzeug.serving
    server = werkzeug.serving.make_server(host, port, _app)
    logger.info(f"PetBot HTTP bridge listening on http://{host}:{port}")
    server.serve_forever()


class MinecraftBridge:
    def __init__(self, host: str = "0.0.0.0", port: int = 5050, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._server_thread: Optional[threading.Thread] = None

    def start(self):
        """Start HTTP server."""
        if self._server_thread and self._server_thread.is_alive():
            return
        t = threading.Thread(
            target=_start_http_server,
            args=(self.host, self.port),
            daemon=True,
            name="petbot-http-bridge",
        )
        t.start()
        self._server_thread = t
        time.sleep(0.3)
        logger.info("MinecraftBridge started.")

    def get_context(self) -> dict:
        """Get latest world state."""
        return get_context()

    def get_chat_messages(self) -> list:
        """Get player chat messages."""
        with _chat_lock:
            msgs = list(_chat_queue)
            _chat_queue.clear()
        return msgs

    def _send(self, action: str, **kwargs) -> bool:
        """Send command and wait for result."""
        cmd = {"action": action, **kwargs}
        cmd_id = _enqueue(cmd)
        result = _wait_result(cmd_id, self.timeout)
        if result is None:
            logger.warning(f"Timeout waiting for result of: {action}")
            return False
        return result.get("ok", False)

    def _send_data(self, action: str, **kwargs) -> Optional[Any]:
        """Send command and get data result."""
        cmd = {"action": action, **kwargs}
        cmd_id = _enqueue(cmd)
        result = _wait_result(cmd_id, self.timeout)
        return result.get("data") if result else None

    # ── MOVEMENT ──────────────────────────────────────────────────────────

    def move(self, direction: str, distance: float = 1.0) -> bool:
        """
        Move in direction with distance.

        Args:
            direction: forward | backward | left | right
            distance: blocks to move (1.0 = 1 block, 3.0 = 3 blocks, etc)
        """
        return self._send("move", direction=direction, distance=distance)

    def stop(self) -> bool:
        """Stop all movement immediately."""
        return self._send("stop")

    def jump(self) -> bool:
        """Jump."""
        return self._send("jump")

    def sneak(self, enable: bool = True) -> bool:
        """Toggle sneaking."""
        return self._send("sneak", enable=enable)

    def sprint(self, enable: bool = True) -> bool:
        """Toggle sprinting."""
        return self._send("sprint", enable=enable)

    # ── LOOKING ───────────────────────────────────────────────────────────

    def look_direction(self, direction: str) -> bool:
        """Look in cardinal direction: north|south|east|west|up|down"""
        return self._send("look", direction=direction)

    def look_rotation(self, yaw: float, pitch: float) -> bool:
        """Look at absolute rotation."""
        return self._send("look", yaw=yaw, pitch=pitch)

    def turn(self, direction: str) -> bool:
        """Turn relative: left|right|back"""
        return self._send("turn", direction=direction)

    # ── INVENTORY ─────────────────────────────────────────────────────────

    def hotbar(self, slot: int) -> bool:
        """Switch to hotbar slot (0-8)."""
        return self._send("hotbar", slot=slot)

    def drop(self, what: str = "mainhand") -> bool:
        """Drop item: mainhand|offhand|all"""
        return self._send("drop", what=what)

    # ── ACTIONS ───────────────────────────────────────────────────────────

    def use(self, mode: str = "once") -> bool:
        """Right-click: once|continuous"""
        return self._send("use", mode=mode)

    def attack(self, mode: str = "once") -> bool:
        """Left-click: once|continuous"""
        return self._send("attack", mode=mode)

    def sit(self) -> bool:
        """Sit (JustSit mod)."""
        return self._send("sit")

    def chat(self, message: str) -> bool:
        """Say something in chat."""
        cmd_id = str(uuid.uuid4())[:8]
        cmd = {"action": "chat", "message": message, "id": cmd_id}
        _pending.append(cmd)
        return True

    # ── BLOCKS ────────────────────────────────────────────────────────────

    def mine_block(self, x: int, y: int, z: int) -> bool:
        """Mine block at coordinates."""
        return self._send("mine", x=x, y=y, z=z)

    def place_block(self, x: int, y: int, z: int, block_type: str) -> bool:
        """Place block at coordinates."""
        return self._send("place", x=x, y=y, z=z, block_type=block_type)

    def interact_block(self, x: int, y: int, z: int) -> bool:
        """Interact with block."""
        return self._send("interact", x=x, y=y, z=z)

    # ── MOD-SPECIFIC ──────────────────────────────────────────────────────

    def place_furniture(self, x: int, y: int, z: int, furniture_type: str) -> bool:
        """Place furniture (MrCrayfish mod)."""
        return self._send("place_furniture", x=x, y=y, z=z, furniture_type=furniture_type)

    def search_jei(self, item_name: str) -> List[str]:
        """Search JEI."""
        data = self._send_data("jei_search", item_name=item_name)
        return data if isinstance(data, list) else []

    def execute_command(self, command: str) -> str:
        """Execute raw Minecraft command."""
        data = self._send_data("raw_command", command=command)
        return str(data) if data else ""

    # ── LEGACY ALIASES ────────────────────────────────────────────────────

    def move_player(self, direction: str, distance: float = 1.0) -> bool:
        return self.move(direction, distance)

    def stop_player(self) -> bool:
        return self.stop()

    def hold_slot(self, slot: int) -> bool:
        return self.hotbar(slot)

    def look(self, yaw: float, pitch: float) -> bool:
        return self.look_rotation(yaw, pitch)

    def click_block(self, x: int, y: int, z: int) -> bool:
        return self.interact_block(x, y, z)