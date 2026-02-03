import pyautogui
import memory
import pygetwindow as gw
import personalityEngine
import tempfile
import os
import subprocess
import sys
import shutil
import platform
import logging
from llm.ollama_client import LLMClient
from llm.response_parser import parse_intent
from duckduckgo_search import DDGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class agents:

    def __init__(self):
        # basic state
        self.mood = personalityEngine.EmotionalState
        self.intent = None
        self.taskDone = True
        # try to initialize optional memory module if available
        try:
            self.memory = memory.Memory()
        except Exception:
            self.memory = None

        # lightweight LLM client that can be used for decisions where appropriate
        try:
            self.llm = LLMClient(model_name="gemma3:4b")
        except Exception:
            self.llm = None

    def get_active_app(self) -> [str]:
        fg = gw.getActiveWindow()
        if fg and fg.title:
            return fg.title
        return None

    def take_screenshot(self):
        path = None
        try:
            img = pyautogui.screenshot()

            with tempfile.NamedTemporaryFile(
                    suffix=".png",
                    delete=False
            ) as tmp:
                path = tmp.name
                img.save(path)

            # Hand off to vision pipeline
            self.handle({
                "type": "VISION_SNAPSHOT",
                "path": path,
                "source": "desktop"
            })

        finally:
            # remove the temporary file; vision should have already processed it
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    logger.exception("Failed to remove temporary screenshot")

    def searchWeb(self, query):
        """Run a DuckDuckGo search and return a cleaned list of results.
        Uses duckduckgo_search.DDGS.text which yields dicts with keys like
        'title', 'body', and 'href'. Returns a list of simplified dicts.
        """
        if not query:
            return []

        results = []
        try:
            with DDGS() as ddgs:
                # limit results to keep response small
                for r in ddgs.text(query, max_results=5):
                    # ddgs yields simple dicts; make a safe mapping
                    results.append({
                        "title": r.get("title") or "",
                        "snippet": r.get("body") or r.get("snippet") or "",
                        "url": r.get("href") or r.get("url") or "",
                    })
        except Exception:
            logger.exception("searchWeb failed")

        return results

    def openApp(self, app: str) -> bool:
        """Attempt to open an application by name. Returns True on success.
        Tries platform-appropriate methods and common fallbacks.
        """
        if not app:
            return False

        app = app.strip()

        # Try to find executable on PATH first
        candidate = shutil.which(app) or shutil.which(app.lower()) or shutil.which(app + '.exe')
        if candidate:
            try:
                subprocess.Popen([candidate])
                return True
            except Exception:
                logger.exception("Failed launching candidate executable: %s", candidate)

        try:
            if sys.platform.startswith('win'):
                # try common Windows exe pattern
                try:
                    subprocess.Popen([app + '.exe'])
                    return True
                except FileNotFoundError:
                    # fall back to os.startfile if full path known
                    try:
                        os.startfile(app)
                        return True
                    except Exception:
                        pass

            elif sys.platform == 'darwin':
                subprocess.Popen(['open', '-a', app])
                return True

            else:
                # linux/unix: try to call by name
                subprocess.Popen([app])
                return True

        except Exception:
            logger.exception("openApp failed for %s", app)

        return False

    def vision(self, path):
        """Describe an image using the configured vision LLM (best-effort).
        Currently this sends a simple prompt; in future pass the image bytes
        if the model supports multimodal input.
        """
        try:
            llm = LLMClient(model_name="llava")
            resp_text = llm.chat([
                {"role": "user", "content": "Describe this screenshot"}
            ])
            summary = resp_text
            return summary
        except Exception:
            logger.exception("vision failed")
            return "(vision unavailable)"

    # helper funcs TODO:need to add y/n for mouse and keyboard realated actions
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

    def send_message(self, text: str):
        # placeholder: integrate with UI or chat system later
        logger.info("send_message: %s", text)
        return True

    # public event handler ---------------------------------------------------------
    def handle(self, event):
        if event.get("type") == "VISION_SNAPSHOT":
            path = event.get("path")
            summary = self.vision(path)
            if self.memory:
                try:
                    self.memory.add("vision", summary)
                except Exception:
                    logger.exception("failed to write to memory")

            # optionally feed summary to LLM for decision-making
            if self.llm:
                try:
                    intent = self.llm.decide(summary)
                except Exception:
                    intent = None
            else:
                intent = None

            if intent:
                self.execute(intent)

        elif event.get("type") == "STT_COMMAND":
            # STT pipeline produces text that we send to the LLM to parse into intents
            text = event.get("text", "")
            try:
                llm = LLMClient(model_name="gemma3:4b")
                resp_text = llm.chat([
                    {"role": "system", "content": open("llm/prompts/personality.txt").read()},
                    {"role": "system", "content": open("llm/prompts/reasoning.txt").read()},
                    {"role": "user", "content": text}
                ])
                intent = parse_intent(resp_text)
            except Exception:
                logger.exception("STT handling failed")
                intent = None

            if intent:
                if intent.get("intent") == "DONE":
                    self.taskDone = True
                else:
                    self.execute(intent)
                    self.taskDone = False

    # main executor ---------------------------------------------------------------
    def execute(self, intent):
        """Execute a parsed intent dict. Returns result or None.
        Expected format: {"intent": "NAME", "args": {...}}
        """
        if not intent or "intent" not in intent:
            logger.warning("execute called with invalid intent: %s", intent)
            return None

        name = intent.get("intent")
        args = intent.get("args", {}) or {}

        logger.info("Executing intent %s with args %s", name, args)

        if name == "TAKE_SCREENSHOT":
            return self.take_screenshot()

        if name == "OPEN_APP":
            app = args.get("app")
            return self.openApp(app)

        if name == "SEARCH_WEB":
            query = args.get("query")
            return self.searchWeb(query)

        if name == "SEND_MESSAGE":
            text = args.get("text")
            return self.send_message(text)

        if name == "CLICK":
            x = args.get("x")
            y = args.get("y")
            return self.click(x, y)

        if name == "TYPE":
            text = args.get("text")
            return self.type_text(text)

        if name == "MOVE_MOUSE":
            x = args.get("x")
            y = args.get("y")
            return self.move_mouse(x, y)

        if name == "DONE":
            self.taskDone = True
            return True

        logger.warning("Unknown intent: %s", name)
        return None