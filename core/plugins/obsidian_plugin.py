from datetime import datetime
from pathlib import Path

from core.local_agent_service import LocalAgentService
from core.mcp_client import MCPClient, MCPClientConfig


class ObsidianPlugin:
    name = "obsidian"

    def __init__(self, context=None):
        self.context = context or {}
        self.agent_service = LocalAgentService()

        try:
            from core.config import (
                MCP_OBSIDIAN_HOST,
                MCP_OBSIDIAN_PORT,
                MCP_OBSIDIAN_COMMAND,
                MCP_TIMEOUT,
            )
            cfg = MCPClientConfig(
                host=MCP_OBSIDIAN_HOST,
                port=MCP_OBSIDIAN_PORT,
                command=MCP_OBSIDIAN_COMMAND,
                timeout=MCP_TIMEOUT,
            )
        except Exception:
            cfg = MCPClientConfig()
        self.mcp = MCPClient(cfg)

    def handle_command(self, text: str):
        raw = (text or "").strip()
        lower = raw.lower()
        if not lower.startswith("obsidian"):
            return False, None

        payload = raw[len("obsidian"):].strip()

        if payload.startswith("append "):
            note_text = payload[len("append "):].strip()
            return True, self._append_note(note_text)

        if payload in ("daily", "daily note"):
            return True, self._create_daily_note()

        if payload.startswith("query "):
            query = payload[len("query "):].strip()
            return True, self._query_note(query)

        if payload.startswith("plan "):
            topic = payload[len("plan "):].strip()
            return True, self.agent_service.create_outline(topic)

        if payload.startswith("graph "):
            topic = payload[len("graph "):].strip()
            return True, self.agent_service.create_graph(topic)

        return True, (
            "Obsidian commands: 'obsidian append <text>', 'obsidian daily', "
            "'obsidian query <text>', 'obsidian plan <topic>', 'obsidian graph <topic>'"
        )

    def _append_note(self, note_text: str) -> str:
        if not note_text:
            return "Nothing to append."

        response = self.mcp.call("append_note", {"text": note_text})
        if response.get("ok"):
            return "Appended note to Obsidian via MCP."

        fallback = self._fallback_file()
        with fallback.open("a", encoding="utf-8") as f:
            f.write(f"- {note_text}\n")
        return f"MCP unavailable. Saved note locally at {fallback}."

    def _create_daily_note(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        items_source = self.context.get("recent_items", [])
        if callable(items_source):
            try:
                resolved_items = items_source()
            except Exception as e:
                print(f"Obsidian recent_items provider error: {e}")
                resolved_items = []
        else:
            resolved_items = items_source
        summary = self.agent_service.daily_summary(resolved_items)

        response = self.mcp.call("create_daily_note", {"date": today, "content": summary})
        if response.get("ok"):
            return "Created daily note in Obsidian via MCP."

        fallback = self._fallback_file(name=f"{today}.md")
        with fallback.open("w", encoding="utf-8") as f:
            f.write(f"# Daily Note {today}\n\n{summary}\n")
        return f"MCP unavailable. Created local daily note at {fallback}."

    def _query_note(self, query: str) -> str:
        if not query:
            return "Please provide text to query."

        response = self.mcp.call("query_note", {"query": query})
        if response.get("ok"):
            result = response.get("result") or response.get("raw") or "No result"
            return f"Obsidian query result: {result}"

        fallback = self._fallback_file()
        if fallback.exists():
            lines = fallback.read_text(encoding="utf-8").splitlines()
            matches = [ln for ln in lines if query.lower() in ln.lower()]
            if matches:
                return "Local note matches:\n" + "\n".join(matches[:8])
        return "No matching notes found."

    def _fallback_file(self, name="obsidian_notes.md") -> Path:
        base = Path.home() / ".local" / "share" / "DesktopPetML"
        base.mkdir(parents=True, exist_ok=True)
        return base / name
