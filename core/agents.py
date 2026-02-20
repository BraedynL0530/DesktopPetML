"""
core/agents.py
Main agent class — handles all intents from LLM.
Now properly initializes MinecraftAgent when a bridge is provided,
and routes STT through the Minecraft system prompt when in-game.
"""
import pyautogui
from core import memory
import pygetwindow as gw
from core import personalityEngine
import tempfile
import os
import subprocess
import sys
import shutil
import platform
import logging
from typing import Optional
from llm.ollama_client import LLMClient
from llm.response_parser import parse_intent
from duckduckgo_search import DDGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Minecraft window title keywords — used to detect MC context
_MC_WINDOW_KEYWORDS = ['minecraft', 'java edition', 'fabric']


class agents:

    def __init__(self, mc_bridge=None):
        self.mood = personalityEngine.EmotionalState
        self.intent = None
        self.taskDone = True

        try:
            self.memory = memory.Memory()
        except Exception:
            self.memory = None

        try:
            self.llm = LLMClient(model_name="gemma3:4b")
        except Exception:
            self.llm = None

        # ── Minecraft agent (only if bridge provided) ──────────────────────
        self.minecraft_agent = None
        if mc_bridge is not None:
            try:
                from minecraft.minecraft_agent import MinecraftAgent
                self.minecraft_agent = MinecraftAgent(mc_bridge)
                logger.info("MinecraftAgent initialized")
            except Exception as e:
                logger.warning(f"MinecraftAgent init failed: {e}")

    # ── Helpers ────────────────────────────────────────────────────────────

    def get_active_app(self) -> Optional[str]:
        fg = gw.getActiveWindow()
        if fg and fg.title:
            return fg.title
        return None

    def _is_minecraft_active(self) -> bool:
        """
        Return True if we should use Minecraft mode.
        Checks window title first, then falls back to whether we have
        live context from Scarpet (handles the case where clicking the
        pet window steals focus away from Minecraft).
        """
        app = self.get_active_app()
        if app:
            app_lower = app.lower()
            if any(kw in app_lower for kw in _MC_WINDOW_KEYWORDS):
                return True
        # Fallback: if Scarpet is actively pushing context, MC is running
        if self.minecraft_agent:
            ctx = self.minecraft_agent.mc.get_context()
            if ctx:
                return True
        return False

    def poll_minecraft_chat(self):
        """
        Call this periodically — checks if Scarpet forwarded any player
        chat and has PetBot respond via the Minecraft LLM path.
        """
        if not self.minecraft_agent:
            return
        try:
            messages = self.minecraft_agent.mc.get_chat_messages()
            for msg in messages:
                player = msg.get("player", "")
                text = msg.get("message", "")
                # Don't respond to PetBot's own messages
                if player.lower() == "petbot":
                    continue
                logger.info(f"MC chat from {player}: {text}")
                self._handle_minecraft_stt(f"{player} said: {text}")
        except Exception:
            logger.exception("poll_minecraft_chat failed")

    def _load_prompt(self, path: str, fallback: str = "") -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return fallback

    # ── Actions ────────────────────────────────────────────────────────────

    def take_screenshot(self):
        path = None
        try:
            img = pyautogui.screenshot()
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                path = tmp.name
                img.save(path)
            self.handle({"type": "VISION_SNAPSHOT", "path": path, "source": "desktop"})
        finally:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    logger.exception("Failed to remove temp screenshot")

    def searchWeb(self, query):
        if not query:
            return []
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=5):
                    results.append({
                        "title":   r.get("title") or "",
                        "snippet": r.get("body") or r.get("snippet") or "",
                        "url":     r.get("href") or r.get("url") or "",
                    })
        except Exception:
            logger.exception("searchWeb failed")
        return results

    def openApp(self, app: str) -> bool:
        if not app:
            return False
        app = app.strip()
        candidate = shutil.which(app) or shutil.which(app.lower()) or shutil.which(app + '.exe')
        if candidate:
            try:
                subprocess.Popen([candidate])
                return True
            except Exception:
                logger.exception("Failed launching: %s", candidate)
        try:
            if sys.platform.startswith('win'):
                try:
                    subprocess.Popen([app + '.exe'])
                    return True
                except FileNotFoundError:
                    try:
                        os.startfile(app)
                        return True
                    except Exception:
                        pass
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', '-a', app])
                return True
            else:
                subprocess.Popen([app])
                return True
        except Exception:
            logger.exception("openApp failed for %s", app)
        return False

    def vision(self, path):
        try:
            llm = LLMClient(model_name="llava")
            return llm.chat([{"role": "user", "content": "Describe this screenshot"}])
        except Exception:
            logger.exception("vision failed")
            return "(vision unavailable)"

    def click(self, x: int, y: int):
        try:
            pyautogui.click(x, y)
            return True
        except Exception:
            logger.exception("click failed")
            return False

    def type_text(self, text: str):
        try:
            pyautogui.typewrite(text)
            return True
        except Exception:
            logger.exception("type_text failed")
            return False

    def move_mouse(self, x: int, y: int):
        try:
            pyautogui.moveTo(x, y)
            return True
        except Exception:
            logger.exception("move_mouse failed")
            return False

    def verify(self):
        pass

    # ── Event handler ──────────────────────────────────────────────────────

    def handle(self, event):
        etype = event.get("type")

        if etype == "VISION_SNAPSHOT":
            path = event.get("path")
            summary = self.vision(path)
            if self.memory:
                try:
                    self.memory.add("vision", summary)
                except Exception:
                    logger.exception("memory write failed")
            if self.llm:
                try:
                    intent = self.llm.decide(summary)
                except Exception:
                    intent = None
            else:
                intent = None
            if intent:
                self.execute(intent)

        elif etype == "STT_COMMAND":
            text = event.get("text", "")

            # ── Route to Minecraft LLM if Minecraft window is active ───────
            if self._is_minecraft_active() and self.minecraft_agent:
                self._handle_minecraft_stt(text)
            else:
                self._handle_desktop_stt(text)

        elif etype == "MINECRAFT_COMMAND":
            if self.minecraft_agent:
                self.minecraft_agent.handle_intent(event.get("intent", {}))
            else:
                logger.warning("MINECRAFT_COMMAND received but no minecraft_agent initialized")

    def _handle_desktop_stt(self, text: str):
        """Route STT through normal desktop personality + reasoning prompts."""
        try:
            personality = self._load_prompt(
                "llm/prompts/personality.txt",
                "You are a helpful desktop assistant."
            )
            reasoning = self._load_prompt(
                "llm/prompts/reasoning.txt",
                "Analyze input and return JSON intent."
            )
            resp_text = self.llm.chat([
                {"role": "system", "content": personality},
                {"role": "system", "content": reasoning},
                {"role": "user",   "content": text},
            ])
            intent = parse_intent(resp_text)
        except Exception:
            logger.exception("Desktop STT handling failed")
            intent = None

        if intent:
            if intent.get("intent") == "DONE":
                self.taskDone = True
            else:
                self.execute(intent)
                self.taskDone = False

    def _handle_minecraft_stt(self, text: str):
        """Route chat/STT through Minecraft LLM with world context."""
        try:
            mc_prompt = self._load_prompt(
                "llm/minecraft_system_prompt.txt",
                "You are PetBot. Return JSON: {\"intent\": \"MINECRAFT_CHAT\", \"args\": {\"message\": \"reply\"}}"
            )

            # Build context string from bridge if available
            context_section = ""
            if self.minecraft_agent:
                ctx = self.minecraft_agent.build_context_string()
                if ctx and ctx != "No context yet — PetBot may still be loading.":
                    context_section = f"\nCURRENT WORLD STATE:\n{ctx}\n"

            messages = [
                {"role": "system", "content": mc_prompt + context_section},
                {"role": "user",   "content": text},
            ]

            resp_text = self.llm.chat(messages)
            logger.info(f"[MC LLM] raw: {repr(resp_text[:300])}")

            intent = parse_intent(resp_text)
            logger.info(f"[MC LLM] parsed intent: {intent}")

        except Exception:
            logger.exception("Minecraft STT handling failed")
            intent = None

        if not intent:
            logger.warning("[MC LLM] No valid intent parsed — no action taken")
            return

        intent_name = intent.get("intent", "")
        if intent_name.startswith("MINECRAFT_"):
            self.minecraft_agent.handle_intent(intent)
        elif intent_name == "DONE":
            self.taskDone = True

    # ── Executor ───────────────────────────────────────────────────────────

    def execute(self, intent):
        if not intent or "intent" not in intent:
            logger.warning("execute called with invalid intent: %s", intent)
            return None

        name = intent.get("intent")
        args = intent.get("args", {}) or {}

        logger.info("Executing intent %s with args %s", name, args)

        # Route Minecraft intents directly
        if name.startswith("MINECRAFT_"):
            if self.minecraft_agent:
                return self.minecraft_agent.handle_intent(intent)
            else:
                logger.warning("Minecraft intent but no agent: %s", name)
                return None

        if name == "TAKE_SCREENSHOT":
            return self.take_screenshot()
        if name == "OPEN_APP":
            return self.openApp(args.get("app"))
        if name == "SEARCH_WEB":
            return self.searchWeb(args.get("query"))
        if name == "CLICK":
            if self.verify() is True:
                return self.click(args.get("x"), args.get("y"))
        if name == "TYPE":
            if self.verify() is True:
                return self.type_text(args.get("text"))
        if name == "MOVE_MOUSE":
            if self.verify() is True:
                return self.move_mouse(args.get("x"), args.get("y"))
        if name == "DONE":
            self.taskDone = True
            return True

        logger.warning("Unknown intent: %s", name)
        return None