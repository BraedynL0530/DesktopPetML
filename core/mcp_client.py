import json
import shlex
import socket
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class MCPClientConfig:
    host: str = "127.0.0.1"
    port: int = 0
    command: str = ""
    timeout: float = 10.0


class MCPClient:
    """Lightweight MCP-like client supporting TCP or command-based transport."""

    def __init__(self, config: MCPClientConfig):
        self.config = config

    def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {},
        }

        if self.config.command:
            return self._call_command(payload)
        if self.config.port:
            return self._call_tcp(payload)

        return {"ok": False, "error": "No MCP transport configured"}

    def _call_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            proc = subprocess.run(
                shlex.split(self.config.command),
                input=json.dumps(payload) + "\n",
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )
            output = (proc.stdout or "").strip().splitlines()
            if not output:
                return {"ok": proc.returncode == 0, "raw": ""}
            last = output[-1]
            try:
                return json.loads(last)
            except Exception:
                return {"ok": proc.returncode == 0, "raw": last}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _call_tcp(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with socket.create_connection((self.config.host, self.config.port), timeout=self.config.timeout) as sock:
                sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                sock.settimeout(self.config.timeout)
                data = sock.recv(65535).decode("utf-8", errors="ignore").strip()
            if not data:
                return {"ok": True, "raw": ""}
            try:
                return json.loads(data)
            except Exception:
                return {"ok": True, "raw": data}
        except Exception as e:
            return {"ok": False, "error": str(e)}
