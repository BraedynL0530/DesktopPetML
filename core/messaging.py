import threading
import time
import random
import re
from typing import Callable, Optional
from core.short_memory import ShortTermMemory
from llm.ollama_client import LLMClient

# Try to import your personality engine; if it isn't available, fall back.
try:
    from core.personalityEngine import AdvancedPersonality as PersonalityEngine
except Exception:
    PersonalityEngine = None

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
        self.chatHistory = []

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
    Periodically generate messages for the UI
    """
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
        self.memory = memory if memory else ShortTermMemory()
        self.interval = interval
        self._stop = threading.Event()
        self.pet = PetProxy()
        self.gui = GUIProxy(self.show_cb)
        self.mood_lines = mood_lines or DEFAULT_MOOD_LINES
        self.max_retry = max_retry

        # Try to load personality engine
        self.engine = None
        if PersonalityEngine:
            try:
                self.engine = PersonalityEngine(self.pet, self.gui, self.mood_lines)
            except Exception as e:
                print(f"Personality engine failed to load: {e}")
                self.engine = None

        # Try to load LLM
        try:
            self.llm = LLMClient(model_name=llm_model)
        except Exception as e:
            print(f"LLM failed to load: {e}")
            self.llm = None

        self._jitter = lambda: random.uniform(-0.25, 0.25) * self.interval

    def stop(self):
        self._stop.set()

    def _update_pet_from_memory(self):
        """Populate pet flags from short-term memory heuristics"""
        if not self.memory:
            return
        try:
            recent_visions = getattr(self.memory, "get_recent_visions", lambda **kw: [])()
            recent_chats = getattr(self.memory, "get_recent_chats", lambda **kw: [])()
            self.pet._surprised = len(recent_visions) > 0
            self.pet._curious = len(recent_chats) > 0
        except Exception:
            pass

    def _get_mood(self):
        """Ask personality engine if available, else use heuristics"""
        if self.engine:
            try:
                mood = getattr(self.engine, "getDominantMood", lambda: None)()
                if mood:
                    return mood
            except Exception:
                pass

        # Fallback heuristics
        if self.pet._curious:
            return "curious"
        if self.pet._surprised:
            return "surprised"
        return "smug"

    def _build_prompt(self, mood: str, context_summary: str) -> list:
        """Construct chat prompt for LLM with app context"""
        try:
            with open("llm/prompts/personality.txt", "r", encoding="utf-8") as f:
                personality_sys = f.read()
        except Exception:
            personality_sys = "You are a sassy desktop cat companion. Make short, witty observations about what your human is doing."

        # Extract current app from context if available
        current_app = self.pet._activeApp if self.pet._activeApp != "Unknown" else None
        category = getattr(self.pet, "_last_category", "unknown")

        # Build context-aware prompt
        if current_app and current_app != "Unknown":
            user_msg = (
                f"Your human is currently using: {current_app} (a {category} app)\n"
                f"Mood: {mood}\n"
                f"Recent context: {context_summary if context_summary else 'Nothing much happening.'}\n\n"
                f"Make ONE short, sassy comment about what they're doing right now (1-2 sentences max). "
                f"Be specific to the {category} app they're using. "
                f"Do NOT use phrases like 'As an AI', 'Here is', 'Sure', etc. "
                f"Just a natural, witty observation from a cat watching them work."
            )
        else:
            user_msg = (
                f"Mood: {mood}\n"
                f"Context: {context_summary if context_summary else 'User seems idle.'}\n\n"
                f"Make ONE short comment about the current situation (1-2 sentences). "
                f"Keep it natural and in-character as a sassy cat."
            )

        return [
            {"role": "system", "content": personality_sys},
            {"role": "user", "content": user_msg},
        ]

    def _is_unwanted(self, text: str) -> bool:
        """Return True if text contains assistant/meta phrasing"""
        if not text:
            return True
        if "\n" in text.strip():
            text = text.splitlines()[0].strip()
        if self._BAD_PHRASES_RE.search(text):
            return True
        if len(text) > 220:
            return True
        return False

    def _clean_and_truncate(self, text: str) -> str:
        if not text:
            return ""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return ""
        out = lines[0]
        # Remove surrounding quotes
        if (out.startswith('"') and out.endswith('"')) or (out.startswith("'") and out.endswith("'")):
            out = out[1:-1].strip()
        # Truncate if too long
        if len(out) > 200:
            out = out[:197].rstrip() + "..."
        return out

    def _ask_llm_for_line(self, mood: str, context_summary: str) -> Optional[str]:
        """Try to get a message from LLM"""
        if not self.llm:
            return None

        messages = self._build_prompt(mood, context_summary)

        for attempt in range(self.max_retry):
            try:
                resp = self.llm.chat(messages)
                text = resp.strip() if isinstance(resp, str) else str(resp).strip()

                cleaned = self._clean_and_truncate(text)
                if not self._is_unwanted(cleaned):
                    return cleaned

                # Retry with clarification
                messages.append(
                    {"role": "user", "content": "Try again, shorter and avoid prefatory phrases; just a single line."})
            except Exception as e:
                print(f"LLM error: {e}")
                return None

        return None

    def run(self):
        """Main messenger loop - THIS WAS MISSING!"""
        print("💬 Messenger thread started")

        while not self._stop.is_set():
            try:
                # Update pet state from memory
                self._update_pet_from_memory()

                mood = self._get_mood()
                context_summary = ""
                try:
                    if self.memory:
                        context_summary = getattr(self.memory, "get_context_summary", lambda *a, **k: "")(max_items=8)
                except Exception:
                    context_summary = ""

                sent = False

                # 1) Try LLM generation
                if self.llm:
                    line = self._ask_llm_for_line(mood, context_summary)
                    if line:
                        print(f"🔔 Messenger sending: {line}")
                        if callable(self.show_cb):
                            self.show_cb(line)
                        sent = True

                # 2) Fallback to personality engine
                if not sent and self.engine:
                    try:
                        self.engine.randomTalk()
                        sent = True
                    except Exception:
                        self.engine = None

                # 3) Fallback to simple mood lines
                if not sent:
                    lines = self.mood_lines.get(mood, ["..."])
                    text = random.choice(lines)
                    print(f"🔔 Messenger fallback: {text}")
                    if callable(self.show_cb):
                        self.show_cb(text)

            except Exception as e:
                print(f"Messenger error: {e}")
                import traceback
                traceback.print_exc()

            # Sleep with responsive stop checking
            total = max(1, int(self.interval + self._jitter()))
            for _ in range(total):
                if self._stop.is_set():
                    break
                time.sleep(1)

        print("💬 Messenger thread stopped")