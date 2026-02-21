"""
core/agents.py
Main agent class — handles all intents from LLM.
"""
import pyautogui
from core import memory
import pygetwindow as gw
from core import personalityEngine
import tempfile
import os
import re
import subprocess
import sys
import shutil
import logging
from typing import Optional
from llm.ollama_client import LLMClient
from llm.response_parser import parse_intent
from duckduckgo_search import DDGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

        self.minecraft_agent = None
        if mc_bridge is not None:
            try:
                from minecraft.minecraft_agent import MinecraftAgent
                self.minecraft_agent = MinecraftAgent(mc_bridge)
                logger.info("MinecraftAgent initialized")
            except Exception as e:
                logger.warning(f"MinecraftAgent init failed: {e}")

    def get_active_app(self) -> Optional[str]:
        fg = gw.getActiveWindow()
        if fg and fg.title:
            return fg.title
        return None

    def _is_minecraft_active(self) -> bool:
        app = self.get_active_app()
        if app:
            if any(kw in app.lower() for kw in _MC_WINDOW_KEYWORDS):
                return True
        if self.minecraft_agent:
            ctx = self.minecraft_agent.mc.get_context()
            if ctx:
                return True
        return False

    def poll_minecraft_chat(self):
        if not self.minecraft_agent:
            return
        try:
            messages = self.minecraft_agent.mc.get_chat_messages()
            for msg in messages:
                player = msg.get("player", "")
                text = msg.get("message", "")
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
                    pass

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
                pass
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
            pass
        return False

    def vision(self, path):
        try:
            llm = LLMClient(model_name="llava")
            return llm.chat([{"role": "user", "content": "Describe this screenshot"}])
        except Exception:
            return "(vision unavailable)"

    def click(self, x: int, y: int):
        try:
            pyautogui.click(x, y)
            return True
        except Exception:
            return False

    def type_text(self, text: str):
        try:
            pyautogui.typewrite(text)
            return True
        except Exception:
            return False

    def move_mouse(self, x: int, y: int):
        try:
            pyautogui.moveTo(x, y)
            return True
        except Exception:
            return False

    def verify(self):
        pass

    def handle(self, event):
        etype = event.get("type")

        if etype == "VISION_SNAPSHOT":
            path = event.get("path")
            summary = self.vision(path)
            if self.memory:
                try:
                    self.memory.add("vision", summary)
                except Exception:
                    pass
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
            if self._is_minecraft_active() and self.minecraft_agent:
                self._handle_minecraft_stt(text)
            else:
                self._handle_desktop_stt(text)

        elif etype == "MINECRAFT_COMMAND":
            if self.minecraft_agent:
                self.minecraft_agent.handle_intent(event.get("intent", {}))

    def _handle_desktop_stt(self, text: str):
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

        # FIXED PATH: was "llm/minecraft_system_prompt.txt" (missing prompts/ subdir)
        mc_prompt = self._load_prompt(
            "Minecraft system prompt.txt",
            # Fallback if file missing — still forces JSON
            'IMPORTANT: You must respond with ONLY a JSON object, nothing else.\n'
            'You are PetBot, an AI Minecraft player. Always use this format:\n'
            '{"intent": "MINECRAFT_CHAT", "args": {"message": "your message"}}'
        )

        context_section = ""
        if self.minecraft_agent:
            ctx = self.minecraft_agent.build_context_string()
            if ctx and ctx != "No context yet — PetBot may still be loading.":
                context_section = f"\nCURRENT WORLD STATE:\n{ctx}\n"

        # Reinforce JSON-only for small models like gemma3:4b that ignore system prompts
        user_msg = (
            f"{text}\n\n"
            f"Respond with ONLY a JSON object. No markdown, no text before or after. "
            f"If replying to chat: {{\"intent\": \"MINECRAFT_CHAT\", \"args\": {{\"message\": \"reply here\"}}}}"
        )

        messages = [
            {"role": "system", "content": mc_prompt + context_section},
            {"role": "user",   "content": user_msg},
        ]

        resp_text = ""
        try:
            resp_text = self.llm.chat(messages)
            logger.info(f"[MC LLM] raw: {repr(resp_text[:300])}")
            intent = parse_intent(resp_text)
            logger.info(f"[MC LLM] parsed intent: {intent}")
        except Exception:
            logger.exception("Minecraft STT handling failed")
            intent = None

        if not intent:
            # Fallback: strip any markdown/prose and send whatever text came back as chat
            logger.warning("[MC LLM] No valid intent — using fallback chat")
            if self.minecraft_agent and resp_text:
                cleaned = re.sub(r'[`*#\n]', ' ', resp_text).strip()
                cleaned = re.sub(r'\s+', ' ', cleaned)[:100]
                if cleaned:
                    self.minecraft_agent.handle_intent({
                        "intent": "MINECRAFT_CHAT",
                        "args": {"message": cleaned}
                    })
            return

        intent_name = intent.get("intent", "")
        if intent_name.startswith("MINECRAFT_"):
            self.minecraft_agent.handle_intent(intent)
        elif intent_name == "DONE":
            self.taskDone = True

    def execute(self, intent):
        if not intent or "intent" not in intent:
            return None

        name = intent.get("intent")
        args = intent.get("args", {}) or {}

        if name.startswith("MINECRAFT_"):
            if self.minecraft_agent:
                return self.minecraft_agent.handle_intent(intent)
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