"""
core/tiered_memory.py
Advanced memory system with importance scoring, time decay, and archival.
Replaces short_memory.py with layered approach: recent → important → archive.
"""

import time
import math
import json
from collections import deque
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta


class TieredMemory:
    """
    Three-layer memory system:

    RECENT LAYER (last 20 events)
    - Full fidelity, always kept
    - Newest first (LIFO)
    - Max 20 items

    IMPORTANT LAYER (scored by relevance)
    - Events with importance > threshold
    - Scored by: type, content, player mentions, recency
    - Max 100 items
    - Decays over time (older items lose importance)

    ARCHIVE LAYER (daily summaries)
    - Old events compressed into summaries
    - One entry per day
    - Accessible but lower priority
    """

    def __init__(self, recent_max: int = 20, important_max: int = 100, importance_threshold: float = 0.4):
        self.recent_max = recent_max
        self.important_max = important_max
        self.importance_threshold = importance_threshold

        # Recent layer: deque of {type, data, timestamp}
        self.recent = deque(maxlen=recent_max)

        # Important layer: list of {type, data, timestamp, importance_score}
        self.important = []

        # Archive layer: dict[date_str] -> {summary, event_count, timestamp}
        self.archive = {}

        # Track event counts for archival
        self._event_counter = 0

    # ────────────────────────────────────────────────────────────────────────
    # ADDING EVENTS
    # ────────────────────────────────────────────────────────────────────────

    def add(self, type_str: str, data: dict):
        """Add event to recent layer and score for important layer."""
        now = time.time()
        event = {
            "type": type_str,
            "data": data,
            "timestamp": now,
        }

        # Always add to recent
        self.recent.append(event)

        # Score and maybe add to important
        score = self._score_importance(type_str, data)
        if score > self.importance_threshold:
            self.important.append({**event, "importance": score})
            self._trim_important()

        self._event_counter += 1

        # Every 100 events, clean up old important entries
        if self._event_counter % 100 == 0:
            self._decay_and_archive()

    def add_chat(self, text: str, who: str = "user"):
        """Add chat event — always important."""
        self.add("chat", {"who": who, "text": text})

    def add_vision(self, summary: str, path: Optional[str] = None):
        """Add vision event."""
        self.add("vision", {"summary": summary, "path": path})

    def add_app_activity(self, app: str, category: str, surprised: bool = False, curious: bool = False):
        """Add app activity event."""
        self.add("app_activity", {
            "app": app,
            "category": category,
            "surprised": surprised,
            "curious": curious
        })

    # ────────────────────────────────────────────────────────────────────────
    # SCORING IMPORTANCE
    # ────────────────────────────────────────────────────────────────────────

    def _score_importance(self, event_type: str, data: dict) -> float:
        """Score event importance 0.0-1.0 based on content & type."""
        score = 0.0

        # Type-based scoring
        type_scores = {
            "chat": 0.9,  # Chat is very important
            "vision": 0.6,  # Vision is moderately important
            "app_activity": 0.3,  # App changes are lower priority
            "location": 0.5,  # Location/position changes
            "inventory": 0.4,  # Inventory changes
            "skill": 0.8,  # New skills learned
            "preference": 0.9,  # Player preferences stated
        }
        score += type_scores.get(event_type, 0.4)

        # Content-based scoring
        if event_type == "chat":
            text = data.get("text", "").lower()
            # Check for emphatic keywords
            emphatic_words = ["remember", "important", "forever", "always", "never",
                              "hate", "love", "favorite", "rule", "must"]
            if any(word in text for word in emphatic_words):
                score += 0.2
            # Check for names (usually capitalized)
            if any(word[0].isupper() for word in text.split() if len(word) > 2):
                score += 0.15
            # Check for numbers (coordinates, inventory slots, etc)
            if any(char.isdigit() for char in text):
                score += 0.1
            # Questions are important
            if "?" in text:
                score += 0.15

        elif event_type == "vision":
            summary = data.get("summary", "").lower()
            # If vision mentions specific items or changes
            if any(word in summary for word in ["item", "change", "new", "danger", "threat"]):
                score += 0.2

        # Cap at 1.0
        return min(score, 1.0)

    # ────────────────────────────────────────────────────────────────────────
    # MEMORY DECAY & ARCHIVAL
    # ────────────────────────────────────────────────────────────────────────

    def _decay_and_archive(self):
        """Time-decay importance scores and archive very old events."""
        now = time.time()
        one_hour = 3600
        one_day = 86400

        # Decay: old events lose importance exponentially
        decayed = []
        for event in self.important:
            age_seconds = now - event["timestamp"]
            # Importance decays by 50% every hour
            decay_factor = 0.5 ** (age_seconds / one_hour)
            decayed_score = event["importance"] * decay_factor
            if decayed_score > 0.1:  # Keep if still somewhat important
                event["importance"] = decayed_score
                decayed.append(event)
            elif age_seconds > one_day:  # Archive if older than 1 day AND decayed
                self._archive_event(event)

        self.important = decayed

    def _archive_event(self, event: dict):
        """Move event to archive layer."""
        ts = event["timestamp"]
        date_key = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

        if date_key not in self.archive:
            self.archive[date_key] = {
                "summary": "",
                "event_count": 0,
                "timestamp": ts,
                "events": []  # Keep raw events for context
            }

        # Store the event
        self.archive[date_key]["events"].append(event)
        self.archive[date_key]["event_count"] += 1

        # Update summary if it's a chat
        if event["type"] == "chat":
            who = event["data"].get("who", "")
            text = event["data"].get("text", "")[:50]  # First 50 chars
            summary_line = f"{who}: {text}"
            if summary_line not in self.archive[date_key]["summary"]:
                self.archive[date_key]["summary"] += summary_line + "; "

    def _trim_important(self):
        """Remove lowest-scoring items from important if over limit."""
        if len(self.important) > self.important_max:
            # Sort by importance, keep top N
            self.important.sort(key=lambda e: e["importance"], reverse=True)
            self.important = self.important[:self.important_max]

    # ────────────────────────────────────────────────────────────────────────
    # RETRIEVAL
    # ────────────────────────────────────────────────────────────────────────

    def get_context_summary(self, max_items: int = 15) -> str:
        """Build context string for LLM — recent + important + archive references."""
        lines = []

        # RECENT LAYER (always first)
        recent_list = list(self.recent)
        if recent_list:
            lines.append("=== RECENT (last events) ===")
            for event in recent_list[-5:]:  # Last 5 recent events
                lines.append(self._format_event(event))

        # IMPORTANT LAYER (sorted by importance)
        if self.important:
            lines.append("")
            lines.append("=== IMPORTANT (remembered facts) ===")
            sorted_important = sorted(self.important, key=lambda e: e["importance"], reverse=True)
            for event in sorted_important[:5]:  # Top 5 important
                lines.append(self._format_event(event, show_score=False))

        # ARCHIVE REFERENCES (just mention dates with activity)
        if self.archive:
            lines.append("")
            lines.append("=== ARCHIVE (past sessions) ===")
            recent_dates = sorted(self.archive.keys(), reverse=True)[:3]  # Last 3 days
            for date in recent_dates:
                count = self.archive[date]["event_count"]
                lines.append(f"[{date}] {count} events")

        return "\n".join(lines[:max_items])

    def _format_event(self, event: dict, show_score: bool = False) -> str:
        """Format a single event for display."""
        t = event["type"]
        data = event["data"]

        if t == "chat":
            who = data.get("who", "user")
            text = data.get("text", "")[:80]
            return f"{who}: {text}"

        elif t == "vision":
            summary = data.get("summary", "")[:80]
            return f"[vision] {summary}"

        elif t == "app_activity":
            app = data.get("app", "Unknown")
            cat = data.get("category", "unknown")
            return f"[using] {app} ({cat})"

        elif t == "location":
            pos = data.get("pos", [0, 0, 0])
            return f"[at] {pos[0]}, {pos[1]}, {pos[2]}"

        else:
            return f"[{t}] {str(data)[:60]}"

    def get_recent(self, count: int = 10) -> List[Dict]:
        """Get N recent events."""
        return list(self.recent)[-count:]

    def get_important(self, count: int = 10) -> List[Dict]:
        """Get N most important events."""
        sorted_imp = sorted(self.important, key=lambda e: e["importance"], reverse=True)
        return sorted_imp[:count]

    def get_archive_for_date(self, date_str: str) -> Optional[Dict]:
        """Get archive entry for a specific date (YYYY-MM-DD format)."""
        return self.archive.get(date_str)

    # ────────────────────────────────────────────────────────────────────────
    # STATS
    # ────────────────────────────────────────────────────────────────────────

    def get_memory_stats(self) -> Dict:
        """Get memory usage and density info."""
        return {
            "recent_items": len(self.recent),
            "important_items": len(self.important),
            "archive_days": len(self.archive),
            "total_events": self._event_counter,
            "memory_ratio": len(self.important) / (len(self.recent) + 1),  # Compression ratio
        }

    def clear(self):
        """Clear all memory."""
        self.recent.clear()
        self.important.clear()
        self.archive.clear()
        self._event_counter = 0