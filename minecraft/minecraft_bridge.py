"""
core/minecraft_bridge.py
Bridge between agent intents and Minecraft actions via Scarplet HTTP polling.

Architecture:
  - This Python server exposes a REST API (Flask, default port 5050).
  - The Scarplet script (petbot_main.sc) polls GET /commands every N ticks,
    executes actions in-game, and POSTs results back to /results.
  - /setup command in-game bootstraps the fake player + starts polling.
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

# ---------------------------------------------------------------------------
# Tiny in-process command bus
# ---------------------------------------------------------------------------

_pending: deque = deque()          # commands waiting to be picked up by Scarplet
_results: Dict[str, Any] = {}      # cmd_id -> result payload
_results_lock = threading.Lock()
_result_events: Dict[str, threading.Event] = {}


def _enqueue(cmd: dict) -> str:
    """Add command to queue, return its id."""
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


# ---------------------------------------------------------------------------
# Flask HTTP server (runs in background thread)
# ---------------------------------------------------------------------------

_app = Flask(__name__)


@_app.route("/commands", methods=["GET"])
def get_commands():
    """
    Scarplet polls this endpoint every N ticks.
    Returns up to 10 pending commands as JSON array.
    """
    batch = []
    for _ in range(10):
        if _pending:
            batch.append(_pending.popleft())
        else:
            break
    return jsonify(batch)


@_app.route("/results", methods=["POST"])
def post_results():
    """
    Scarplet posts execution results here.
    Body: [{"id": "abc123", "ok": true, "data": "..."}]
    """
    items = request.get_json(force=True, silent=True) or []
    with _results_lock:
        for item in items:
            cmd_id = item.get("id")
            if cmd_id and cmd_id in _result_events:
                _results[cmd_id] = item
                _result_events[cmd_id].set()
    return jsonify({"ack": len(items)})


@_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "pending": len(_pending)})


def _start_http_server(host: str, port: int):
    import werkzeug.serving
    server = werkzeug.serving.make_server(host, port, _app)
    logger.info(f"PetBot HTTP bridge listening on http://{host}:{port}")
    server.serve_forever()


# ---------------------------------------------------------------------------
# MinecraftBridge
# ---------------------------------------------------------------------------

class MinecraftBridge:
    """
    Sends commands to Minecraft by queuing them for the Scarplet polling loop.
    No RCON required — communication is pure HTTP.

    Quick-start:
      1. Drop petbot_main.sc into your server's /scripts folder.
      2. In-game: /script load petbot_main
      3. In-game: /petbot setup          <- spawns PetBot, sets skin, starts polling
      4. Start this Python bridge.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 5050, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._server_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the HTTP bridge server (non-blocking)."""
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
        time.sleep(0.3)  # let Flask bind
        logger.info("MinecraftBridge started.")

    # ------------------------------------------------------------------
    # Low-level dispatch
    # ------------------------------------------------------------------

    def _send(self, action: str, **kwargs) -> bool:
        """Enqueue an action and wait for Scarplet to confirm it."""
        cmd = {"action": action, **kwargs}
        cmd_id = _enqueue(cmd)
        result = _wait_result(cmd_id, self.timeout)
        if result is None:
            logger.warning(f"Timeout waiting for result of {action}")
            return False
        ok = result.get("ok", False)
        if not ok:
            logger.error(f"Scarplet reported failure for {action}: {result.get('error')}")
        return ok

    def _send_data(self, action: str, **kwargs) -> Optional[Any]:
        """Like _send but returns the full data payload."""
        cmd = {"action": action, **kwargs}
        cmd_id = _enqueue(cmd)
        result = _wait_result(cmd_id, self.timeout)
        if result is None:
            return None
        return result.get("data")

    # ------------------------------------------------------------------
    # Movement & basic interaction
    # ------------------------------------------------------------------

    def move_player(self, direction: str, distance: float = 5.0) -> bool:
        return self._send("move", direction=direction, distance=distance)

    def mine_block(self, x: int, y: int, z: int) -> bool:
        return self._send("mine", x=x, y=y, z=z)

    def place_block(self, x: int, y: int, z: int, block_type: str) -> bool:
        return self._send("place", x=x, y=y, z=z, block_type=block_type)

    def click_block(self, x: int, y: int, z: int, face: str = "north") -> bool:
        return self._send("interact", x=x, y=y, z=z, face=face)

    # ------------------------------------------------------------------
    # Mod-specific actions
    # ------------------------------------------------------------------

    def sit_on_furniture(self, furniture_id: str) -> bool:
        return self._send("sit", furniture_id=furniture_id)

    def place_furniture(self, x: int, y: int, z: int, furniture_type: str) -> bool:
        return self._send("place_furniture", x=x, y=y, z=z, furniture_type=furniture_type)

    def manage_trinket(self, action: str, trinket_type: str) -> bool:
        return self._send("trinket", trinket_action=action, trinket_type=trinket_type)

    def search_jei(self, item_name: str) -> List[str]:
        data = self._send_data("jei_search", item_name=item_name)
        if isinstance(data, list):
            return data
        return []

    # ------------------------------------------------------------------
    # Carpet fake-player control
    # ------------------------------------------------------------------

    def spawn_fake_player(self, name: str, x: int, y: int, z: int) -> bool:
        return self._send("spawn_player", name=name, x=x, y=y, z=z)

    def set_fake_player_skin(self, name: str, skin_url: str) -> bool:
        """
        Set skin for a fake player.
        Requires the skin URL to be a valid Mojang-format skin PNG.
        Handled in Scarplet via the /player <name> skin set <url> Carpet command.
        """
        return self._send("set_skin", name=name, skin_url=skin_url)

    def script_fake_player(self, script_name: str, player_name: str) -> bool:
        return self._send("run_script", script_name=script_name, player_name=player_name)

    def fake_player_action(self, player_name: str, action: str, **kwargs) -> bool:
        return self._send("player_action", player_name=player_name, action=action, **kwargs)

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def execute_command(self, command: str) -> str:
        data = self._send_data("raw_command", command=command)
        return str(data) if data else ""