import time
from collections import deque
from typing import List, Dict, Optional


class ShortTermMemory:
    """
    Extended short-term memory for quick context:
    - stores generic events
    - convenience methods for chats + vision summaries
    """

    def __init__(self, max_items: int = 500):
        self.events = deque(maxlen=max_items)  # each event is dict: {type, data, timestamp}

    def add(self, type: str, data: dict):
        self.events.append({
            "type": type,
            "data": data,
            "timestamp": time.time()
        })

    def add_chat(self, text: str, who: str = "user"):
        """Store a chat / speech event"""
        self.add("chat", {"who": who, "text": text})

    def add_vision(self, summary: str, path: Optional[str] = None):
        """Store vision summary + optional path reference"""
        self.add("vision", {"summary": summary, "path": path})

    def get_recent(self, seconds: int = 300) -> List[Dict]:
        cutoff = time.time() - seconds
        return [e for e in self.events if e["timestamp"] >= cutoff]

    def get_recent_chats(self, seconds: int = 600, limit: int = 20) -> List[Dict]:
        chats = [e for e in reversed(self.events) if e["type"] == "chat" and e["timestamp"] >= (time.time() - seconds)]
        # return newest-first up to limit
        return list(reversed(chats[:limit]))

    def get_recent_visions(self, seconds: int = 3600, limit: int = 10) -> List[Dict]:
        visions = [e for e in reversed(self.events) if e["type"] == "vision" and e["timestamp"] >= (time.time() - seconds)]
        return list(reversed(visions[:limit]))

    def get_context_summary(self, max_items: int = 10) -> str:
        """
        Create a short combined textual summary of recent context (mix of chats + vision),
        newest-first truncated to max_items entries.
        """
        recent = list(reversed(list(self.events)))[:max_items]
        lines = []
        for e in recent:
            t = e["type"]
            if t == "chat":
                who = e["data"].get("who", "user")
                text = e["data"].get("text", "")
                lines.append(f"{who}: {text}")
            elif t == "vision":
                summary = e["data"].get("summary", "")
                lines.append(f"[vision] {summary}")
            else:
                lines.append(f"[{t}] {e['data']}")
        return "\n".join(lines)