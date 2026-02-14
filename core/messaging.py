import threading
import time
import random
import re
from typing import Callable, Optional
from core.short_memory import ShortTermMemory
from llm.ollama_client import LLMClient

# Try to import your personality engine; if it isn't available, fall back.
try:
    from core.personalityEngine import personalityEngine as _pe
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
    Fixed constructor: memory should be an object, NOT a path or anything else.
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
        llm_model: str = "gemma:2b",
        max_retry: int = 3,
    ):
        super().__init__(daemon=True)
        self.show_cb = show_callback
        # 👇 This is the key fix:
        self.memory = memory if memory else ShortTermMemory()
        self.interval = interval
        self._stop = threading.Event()
        self.pet = PetProxy()
        self.gui = GUIProxy(self.show_cb)
        self.mood_lines = mood_lines or DEFAULT_MOOD_LINES
        self.max_retry = max_retry

        self.engine = None
        if _pe:
            try:
                EngineClass = getattr(_pe, "PersonalityEngine", None) or getattr(_pe, "personalityEngine", None)
                if EngineClass:
                    self.engine = EngineClass(self.pet, self.gui, self.mood_lines)
            except Exception:
                self.engine = None

        try:
            self.llm = LLMClient(model_name=llm_model)
        except Exception:
            self.llm = None

        self._jitter = lambda: random.uniform(-0.25, 0.25) * self.interval

    # ...[rest of class unchanged, matches your logic for update, mood, prompt, etc.]...