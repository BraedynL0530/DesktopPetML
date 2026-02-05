import threading
import time
import random
import re
from typing import Callable, Optional

from llm.ollama_client import LLMClient

# Try to import your personality engine; if it isn't available fall back.
try:
    import personalityEngine as _pe
except Exception:
    _pe = None

DEFAULT_MOOD_LINES = {
    "smug": [
        "You and me, buddy. What a day.",
        "I see you there. Working hard?",
        "Hmph. Humans and their tiny problems."
    ],
    "curious": [
        "What's that you're doing? Looks interesting.",
        "That caught my eye — what's next?",
        "Ooo, tell me more about that."
    ],
    "surprised": [
        "Whoa, didn't expect that!",
        "Huh — fancy.",
        "Hey, that's new!"
    ],
    "bored": [
        "I'm bored. Entertain me.",
        "Do you have snacks? I have questions.",
        "You should take a break — stare at me for a bit."
    ]
}


class GUIProxy:
    def __init__(self, show_callback: Optional[Callable[[str], None]] = None):
        self._cb = show_callback

    def showChat(self, text: str, duration: int = 4000):
        if callable(self._cb):
            try:
                self._cb(text)
            except Exception:
                pass


class PetProxy:
    def __init__(self):
        self._surprised = False
        self._curious = False
        self._activeApp = "Unknown"
        self.chatHistory = []  # some personality engines expect chatHistory

    @property
    def surprised(self):
        return self._surprised

    @property
    def curious(self):
        return self._curious

    @property
    def activeApp(self):
        return self._activeApp

    def categorize(self, app):
        return getattr(self, "_last_category", "unknown")


class RandomMessenger(threading.Thread):
    """
    Periodically generate dynamic messages for the UI.
    - show_callback(text) delivers text to UI (expected to call UI.showChat)
    - memory: optional ShortTermMemory instance (must implement get_context_summary/get_recent_* helpers)
    - interval: seconds between messages
    - mood_lines: fallback local lines if LLM/engine unavailable
    """

    # regex patterns that indicate assistant/meta phrasing
    _BAD_PHRASES_RE = re.compile(
        r"(?i)\b(here('?s| is)|as an ai|as an ai language model|i can('?t| not)|i am an ai|sure,?|please find|here are)\b"
    )

    def __init__(
        self,
        show_callback: Optional[Callable[[str], None]] = None,
        memory=None,
        interval: int = 30,
        mood_lines=None,
        llm_model: str = "gemma3:4b",
        max_retry: int = 3,
    ):
        super().__init__(daemon=True)
        self.show_cb = show_callback
        self.memory = memory
        self.interval = interval
        self._stop = threading.Event()
        self.pet = PetProxy()
        self.gui = GUIProxy(self.show_cb)
        self.mood_lines = mood_lines or DEFAULT_MOOD_LINES
        self.max_retry = max_retry

        # personality engine (optional)
        self.engine = None
        if _pe:
            try:
                EngineClass = getattr(_pe, "PersonalityEngine", None) or getattr(_pe, "personalityEngine", None)
                if EngineClass:
                    # instantiate (pet, gui, mood_lines) is expected by many variants
                    self.engine = EngineClass(self.pet, self.gui, self.mood_lines)
            except Exception:
                self.engine = None

        # LLM client for dynamic message generation. If the LLM isn't usable we'll fallback.
        try:
            self.llm = LLMClient(model_name=llm_model)
        except Exception:
            self.llm = None

        # small randomness to avoid strict periodicity
        self._jitter = lambda: random.uniform(-0.25, 0.25) * self.interval

    def stop(self):
        self._stop.set()

    def _update_pet_from_memory(self):
        """Populate pet flags from short-term memory heuristics."""
        if not self.memory:
            return
        try:
            recent_visions = getattr(self.memory, "get_recent_visions", lambda **kw: [])()
            recent_chats = getattr(self.memory, "get_recent_chats", lambda **kw: [])()
            self.pet._surprised = len(recent_visions) > 0
            self.pet._curious = len(recent_chats) > 0
            if recent_chats:
                last = recent_chats[-1]["data"].get("text", "")
                # leave activeApp as-is if we have no better hint
                if len(last) < 200:
                    # naive behavior: if they mention "discord" or "chrome", set it — optional
                    if "discord" in last.lower():
                        self.pet._activeApp = "Discord"
            # populate chatHistory used by some personality engines
            if hasattr(self.memory, "get_recent_chats"):
                chats = self.memory.get_recent_chats(seconds=3600, limit=30)
                self.pet.chatHistory = [{"who": c["data"].get("who", "user"), "text": c["data"].get("text", "")} for c in chats]
        except Exception:
            # be resilient to memory API differences
            pass

    def _get_mood(self):
        """Ask personality engine if available, else use simple heuristics."""
        if self.engine:
            try:
                # many personality engines expose getDominantMood()
                mood = getattr(self.engine, "getDominantMood", lambda: None)()
                if mood:
                    return mood
            except Exception:
                pass

        # heuristics
        if self.pet._curious:
            return "curious"
        if self.pet._surprised:
            return "surprised"
        return "smug"

    def _build_prompt(self, mood: str, context_summary: str) -> list:
        """Construct the chat prompt for the LLM client (system + user roles)."""
        # load personality system prompt from file if available
        try:
            with open("llm/prompts/personality.txt", "r", encoding="utf-8") as f:
                personality_sys = f.read()
        except Exception:
            personality_sys = "You are a friendly on-screen pet. Speak playfully and succinctly."

        # user prompt instructing the LLM to produce one short line consistent with mood/context
        user_msg = (
            f"Context (recent activity):\n{context_summary}\n\n"
            f"Mood: {mood}\n\n"
            "Produce exactly one short, natural, casual line the pet would say right now (1-2 short sentences). "
            "Do NOT include prefatory or meta phrases like 'Sure, here's', 'As an AI', 'I cannot', or 'Here is'. "
            "Avoid lists, code, instructions, or mentions of being an AI. Keep it friendly and in-character. "
            "Return only the line (no surrounding quotes)."
        )

        return [
            {"role": "system", "content": personality_sys},
            {"role": "user", "content": user_msg},
        ]

    def _is_unwanted(self, text: str) -> bool:
        """Return True if text contains assistant/meta phrasing we want to avoid."""
        if not text:
            return True
        # one-line only constraint
        if "\n" in text.strip():
            # allow but prefer first line; we'll still check content
            text = text.splitlines()[0].strip()
        # filter known bad phrases
        if self._BAD_PHRASES_RE.search(text):
            return True
        # avoid long/verbose outputs
        if len(text) > 220:
            return True
        # avoid enumerations or code blocks
        if ":" in text and len(text.splitlines()) > 1:
            return True
        # looks okay
        return False

    def _clean_and_truncate(self, text: str) -> str:
        if not text:
            return ""
        # take first non-empty line
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return ""
        out = lines[0]
        # remove surrounding quotes
        if (out.startswith('"') and out.endswith('"')) or (out.startswith("'") and out.endswith("'")):
            out = out[1:-1].strip()
        # simple truncation
        if len(out) > 200:
            out = out[:197].rstrip() + "..."
        return out

    def _ask_llm_for_line(self, mood: str, context_summary: str) -> Optional[str]:
        if not self.llm:
            return None

        messages = self._build_prompt(mood, context_summary)

        # try up to max_retry attempts if we get back assistant-style phrasing
        for attempt in range(self.max_retry):
            try:
                resp = self.llm.chat(messages)
                # resp may be a string or object depending on client; treat conservatively
                if isinstance(resp, str):
                    text = resp.strip()
                else:
                    # try to read 'content' or fallback to str()
                    text = (resp.get("content") if isinstance(resp, dict) else str(resp)).strip()

                cleaned = self._clean_and_truncate(text)
                if not self._is_unwanted(cleaned):
                    return cleaned
                # otherwise try again, optionally add a clarification prompt
                messages.append({"role": "user", "content": "Try again, shorter and avoid prefatory phrases; just a single line."})
            except Exception:
                # on any LLM error, bail out to fallback
                return None

        return None

    def run(self):
        while not self._stop.is_set():
            try:
                # update pet state from memory heuristics
                self._update_pet_from_memory()

                mood = self._get_mood()
                context_summary = ""
                try:
                    if self.memory:
                        # prefer small context summary
                        context_summary = getattr(self.memory, "get_context_summary", lambda *a, **k: "")(max_items=8)
                except Exception:
                    context_summary = ""

                sent = False

                # 1) Prefer dynamic LLM generation
                if self.llm:
                    line = self._ask_llm_for_line(mood, context_summary)
                    if line:
                        # if personalityEngine exists and has talk() we can route through it to keep consistent UI logic
                        if self.engine and hasattr(self.engine, "talk"):
                            try:
                                self.engine.talk(line)
                            except Exception:
                                # fallback to direct UI callback
                                if callable(self.show_cb):
                                    self.show_cb(line)
                        else:
                            if callable(self.show_cb):
                                self.show_cb(line)
                        sent = True

                # 2) If LLM failed or unavailable, try personalityEngine.randomTalk()
                if not sent and self.engine:
                    try:
                        # let engine pick something from its mood_lines and use GUIProxy to show
                        self.engine.randomTalk()
                        sent = True
                    except Exception:
                        self.engine = None

                # 3) fallback to simple local mood_lines
                if not sent:
                    lines = self.mood_lines.get(mood, ["..."])
                    text = random.choice(lines)
                    if callable(self.show_cb):
                        self.show_cb(text)

            except Exception:
                # swallow to avoid killing the thread
                pass

            # sleep (allow responsive stop)
            total = max(1, int(self.interval + self._jitter()))
            for _ in range(total):
                if self._stop.is_set():
                    break
                time.sleep(1)