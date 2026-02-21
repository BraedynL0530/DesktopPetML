"""
minecraft/minecraft_bridge.py
HTTP bridge — Python side. Scarpet polls GET /commands, POSTs results back.
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

_chat_queue: deque = deque()  # incoming MC chat messages for agent to process
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
    with _context_lock:
        return dict(_latest_context)


_app = Flask(__name__)


@_app.route("/commands", methods=["GET"])
def get_commands():
    batch = []
    for _ in range(10):
        if _pending:
            batch.append(_pending.popleft())
        else:
            break
    return jsonify(batch)


@_app.route("/results", methods=["POST"])
def post_results():
    items = request.get_json(force=True, silent=True) or []
    if not isinstance(items, list):
        items = [items]
    with _results_lock:
        for item in items:
            # Scarpet encode_json may produce [[key,val],...] instead of {key:val}
            # Normalise both forms to a dict
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
    data = request.get_json(force=True, silent=True) or {}
    with _context_lock:
        _latest_context.clear()
        _latest_context.update(data)
    return jsonify({"ok": True})


@_app.route("/context", methods=["GET"])
def get_context_endpoint():
    return jsonify(get_context())


@_app.route("/chat", methods=["POST"])
def post_chat():
    """Scarpet forwards player chat here so the agent can respond."""
    data = request.get_json(force=True, silent=True) or {}
    with _chat_lock:
        _chat_queue.append(data)
    return jsonify({"ok": True})


@_app.route("/chat", methods=["GET"])
def get_chat():
    """Agent polls for new chat messages."""
    messages = []
    with _chat_lock:
        while _chat_queue:
            messages.append(_chat_queue.popleft())
    return jsonify(messages)


@_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "pending": len(_pending)})


@_app.route("/inject", methods=["POST"])
def inject():
    """Manual test endpoint — inject a command directly."""
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
        """Latest world state pushed by Scarpet every ~2 seconds."""
        return get_context()

    def get_chat_messages(self) -> list:
        """Drain any player chat messages forwarded by Scarpet."""
        with _chat_lock:
            msgs = list(_chat_queue)
            _chat_queue.clear()
        return msgs

    def _send(self, action: str, **kwargs) -> bool:
        cmd = {"action": action, **kwargs}
        cmd_id = _enqueue(cmd)
        result = _wait_result(cmd_id, self.timeout)
        if result is None:
            logger.warning(f"Timeout waiting for result of: {action}")
            return False
        if not result.get("ok", False):
            logger.error(f"Scarpet error for {action}: {result.get('error')}")
        return result.get("ok", False)

    def _send_data(self, action: str, **kwargs) -> Optional[Any]:
        cmd = {"action": action, **kwargs}
        cmd_id = _enqueue(cmd)
        result = _wait_result(cmd_id, self.timeout)
        return result.get("data") if result else None

    # ── Movement ──────────────────────────────────────────────
    def move(self, direction: str) -> bool:
        """direction: forward | backward | left | right"""
        return self._send("move", direction=direction)

    def stop(self) -> bool:
        return self._send("stop")

    def jump(self) -> bool:
        return self._send("jump")

    def sneak(self, enable: bool = True) -> bool:
        return self._send("sneak", enable=enable)

    def sprint(self, enable: bool = True) -> bool:
        return self._send("sprint", enable=enable)

    # ── Looking ───────────────────────────────────────────────
    def look_direction(self, direction: str) -> bool:
        """direction: north | south | east | west | up | down"""
        return self._send("look", direction=direction)

    def look_rotation(self, yaw: float, pitch: float) -> bool:
        """yaw: 0=south,90=west,180=north,270=east  pitch: -90=up,90=down"""
        return self._send("look", yaw=yaw, pitch=pitch)

    def turn(self, direction: str) -> bool:
        """direction: left | right | back | or yaw/pitch string"""
        return self._send("turn", direction=direction)

    # ── Inventory ─────────────────────────────────────────────
    def hotbar(self, slot: int) -> bool:
        """Switch held item to hotbar slot 0-8."""
        return self._send("hotbar", slot=slot)

    def drop(self, what: str = "mainhand") -> bool:
        """what: mainhand | offhand | all | <slot number>"""
        return self._send("drop", what=what)

    # ── Actions ───────────────────────────────────────────────
    def use(self, mode: str = "once") -> bool:
        """Right-click. mode: once | continuous | interval"""
        return self._send("use", mode=mode)

    def attack(self, mode: str = "once") -> bool:
        """Left-click. mode: once | continuous | interval"""
        return self._send("attack", mode=mode)

    def sit(self) -> bool:
        """Look down + right-click — JustSit intercepts this."""
        return self._send("sit")

    def chat(self, message: str) -> bool:
        """Make PetBot say something — fire and forget, no result wait needed."""
        cmd_id = str(uuid.uuid4())[:8]
        cmd = {"action": "chat", "message": message, "id": cmd_id}
        _pending.append(cmd)
        # Don't create a result event — we don't wait for chat confirmation
        return True

    # ── Blocks ────────────────────────────────────────────────
    def mine_block(self, x: int, y: int, z: int) -> bool:
        return self._send("mine", x=x, y=y, z=z)

    def place_block(self, x: int, y: int, z: int, block_type: str) -> bool:
        return self._send("place", x=x, y=y, z=z, block_type=block_type)

    def interact_block(self, x: int, y: int, z: int) -> bool:
        return self._send("interact", x=x, y=y, z=z)

    # ── Mod-specific ──────────────────────────────────────────
    def place_furniture(self, x: int, y: int, z: int, furniture_type: str) -> bool:
        return self._send("place_furniture", x=x, y=y, z=z, furniture_type=furniture_type)

    def search_jei(self, item_name: str) -> List[str]:
        data = self._send_data("jei_search", item_name=item_name)
        return data if isinstance(data, list) else []

    def spawn_fake_player(self, name: str, x: int, y: int, z: int) -> bool:
        return self._send("spawn_player", name=name, x=x, y=y, z=z)

    def set_skin(self, name: str, skin_url: str) -> bool:
        return self._send("set_skin", name=name, skin_url=skin_url)

    def execute_command(self, command: str) -> str:
        data = self._send_data("raw_command", command=command)
        return str(data) if data else ""

    # ── Legacy aliases for existing code ──────────────────────
    def move_player(self, direction: str, distance: float = 5.0) -> bool:
        return self.move(direction)

    def stop_player(self) -> bool:
        return self.stop()

    def hold_slot(self, slot: int) -> bool:
        return self.hotbar(slot)

    def look(self, yaw: float, pitch: float) -> bool:
        return self.look_rotation(yaw, pitch)

    def click_block(self, x: int, y: int, z: int) -> bool:
        return self.interact_block(x, y, z)