"""
core/agents.py
"""
import pyautogui
from core import memory
import pygetwindow as gw
from core import personalityEngine
import tempfile, os, re, random, subprocess, sys, shutil, logging, threading
from typing import Optional
from llm.ollama_client import LLMClient
from llm.response_parser import parse_intent
from duckduckgo_search import DDGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_MC_WINDOW_KEYWORDS = ['minecraft', 'java edition', 'fabric']

# Direct intent pre-classifier — bypasses LLM for obvious commands
_DIRECT_INTENTS = [
    (r'\b(go|move|walk|step)\s+forward\b',    {"intent": "MINECRAFT_MOVE",   "args": {"direction": "forward"}}),
    (r'\b(go|move|walk|step)\s+back(ward)?\b', {"intent": "MINECRAFT_MOVE",  "args": {"direction": "backward"}}),
    (r'\b(go|move|walk|step)\s+left\b',        {"intent": "MINECRAFT_MOVE",   "args": {"direction": "left"}}),
    (r'\b(go|move|walk|step)\s+right\b',       {"intent": "MINECRAFT_MOVE",   "args": {"direction": "right"}}),
    (r'\bstop( moving)?\b',                    {"intent": "MINECRAFT_STOP",   "args": {}}),
    (r'\bjump\b',                              {"intent": "MINECRAFT_JUMP",   "args": {}}),
    (r'\blook\s+north\b',  {"intent": "MINECRAFT_LOOK", "args": {"direction": "north"}}),
    (r'\blook\s+south\b',  {"intent": "MINECRAFT_LOOK", "args": {"direction": "south"}}),
    (r'\blook\s+east\b',   {"intent": "MINECRAFT_LOOK", "args": {"direction": "east"}}),
    (r'\blook\s+west\b',   {"intent": "MINECRAFT_LOOK", "args": {"direction": "west"}}),
    (r'\blook\s+up\b',     {"intent": "MINECRAFT_LOOK", "args": {"direction": "up"}}),
    (r'\blook\s+down\b',   {"intent": "MINECRAFT_LOOK", "args": {"direction": "down"}}),
    (r'\b(sit|sit\s*down)\b', {"intent": "MINECRAFT_SIT",    "args": {}}),
    (r'\bsprint\b',           {"intent": "MINECRAFT_SPRINT", "args": {"enable": True}}),
    (r'\bsneak\b',            {"intent": "MINECRAFT_SNEAK",  "args": {"enable": True}}),
    (r'\bunsneak\b',          {"intent": "MINECRAFT_SNEAK",  "args": {"enable": False}}),
]


def _get_emotion(obj, name: str, default: float = 50.0) -> float:
    """Safely read an emotion value from whatever EmotionalState looks like."""
    try:
        v = getattr(obj, name, None)
        if v is None:
            v = obj[name] if hasattr(obj, '__getitem__') else default
        return float(v)
    except Exception:
        return default


class agents:

    def __init__(self, mc_bridge=None):
        self.intent = None
        self.taskDone = True

        # PersonalityTraits holds curiosity/boredom/aggression/affection
        try:
            self.traits = personalityEngine.PersonalityTraits()
        except Exception:
            self.traits = None  # dict fallback used in _emotion()

        # _emotions just points at traits for unified access
        self._emotions = self.traits

        try:
            self.memory = memory.Memory()
        except Exception:
            self.memory = None

        try:
            self.llm = LLMClient(model_name="gemma3:4b")
        except Exception as e:
            logger.error(f"LLM init failed: {e}")
            self.llm = None

        self.minecraft_agent = None
        if mc_bridge is not None:
            try:
                from minecraft.minecraft_agent import MinecraftAgent
                self.minecraft_agent = MinecraftAgent(mc_bridge)
                logger.info("MinecraftAgent initialized")
            except Exception as e:
                logger.warning(f"MinecraftAgent init failed: {e}")

        # Goal system
        self._current_goal = None          # e.g. "explore the area"
        self._goal_steps   = []            # list of intent dicts queued from chain-of-thought
        self._goal_lock    = threading.Lock()

    # ── Emotion helpers ───────────────────────────────────────────────────────

    def _emotion(self, name: str, default: float = 50.0) -> float:
        if self.traits is None:
            return default
        # PersonalityTraits uses: curiosity, boredom, aggression, affection
        return float(getattr(self.traits, name, default))

    def _set_emotion(self, name: str, value: float):
        if self.traits is not None:
            try:
                setattr(self.traits, name, max(0.0, min(100.0, float(value))))
            except Exception:
                pass

    # ── App helpers ───────────────────────────────────────────────────────────

    def get_active_app(self) -> Optional[str]:
        try:
            fg = gw.getActiveWindow()
            return fg.title if fg and fg.title else None
        except Exception:
            return None

    def _is_minecraft_active(self) -> bool:
        app = self.get_active_app()
        if app and any(kw in app.lower() for kw in _MC_WINDOW_KEYWORDS):
            return True
        if self.minecraft_agent:
            try:
                return bool(self.minecraft_agent.mc.get_context())
            except Exception:
                pass
        return False

    # ── Minecraft chat polling (called by agent_bridge every 1 s) ─────────────

    def poll_minecraft_chat(self):
        if not self.minecraft_agent:
            return
        try:
            messages = self.minecraft_agent.mc.get_chat_messages()
            for msg in messages:
                player = msg.get("player", "")
                text   = msg.get("message", "")
                if player.lower() == "petbot":
                    continue
                logger.info(f"MC chat from {player}: {text}")
                self._handle_minecraft_stt(f"{player} said: {text}")
        except Exception:
            logger.exception("poll_minecraft_chat failed")

    # ── Goal / chain-of-thought system ───────────────────────────────────────

    def set_goal(self, goal: str):
        """Set a new goal and ask the LLM to plan steps for it."""
        if not self.llm or not self.minecraft_agent:
            return
        logger.info(f"[GOAL] New goal: {goal}")
        self._current_goal = goal

        ctx = ""
        try:
            ctx = self.minecraft_agent.build_context_string()
        except Exception:
            pass

        plan_prompt = (
            "You are PetBot's planner. Given a goal and world context, output a JSON array of "
            "up to 6 sequential Minecraft intent steps. Each step is one intent object.\n"
            "Output ONLY the JSON array, nothing else.\n"
            "Available intents: MINECRAFT_MOVE(direction), MINECRAFT_STOP, MINECRAFT_JUMP, "
            "MINECRAFT_LOOK(direction), MINECRAFT_CHAT(message), MINECRAFT_SIT, MINECRAFT_ATTACK(mode), "
            "MINECRAFT_USE(mode), MINECRAFT_DROP(what).\n"
            f"WORLD STATE:\n{ctx}\n"
            f"GOAL: {goal}\n"
            "Example output:\n"
            '[{"intent":"MINECRAFT_LOOK","args":{"direction":"north"}},{"intent":"MINECRAFT_MOVE","args":{"direction":"forward"}}]'
        )
        try:
            resp = self.llm.chat([{"role": "user", "content": plan_prompt}])
            # Extract JSON array
            match = re.search(r'\[.*\]', resp, re.DOTALL)
            if match:
                import json
                steps = json.loads(match.group())
                with self._goal_lock:
                    self._goal_steps = steps
                logger.info(f"[GOAL] Planned {len(steps)} steps for '{goal}'")
        except Exception as e:
            logger.warning(f"[GOAL] Planning failed: {e}")

    def _execute_next_goal_step(self):
        """Pop and execute the next step in the goal queue."""
        with self._goal_lock:
            if not self._goal_steps:
                return False
            step = self._goal_steps.pop(0)
        try:
            self.minecraft_agent.handle_intent(step)
            logger.info(f"[GOAL] Step executed: {step}")
        except Exception as e:
            logger.warning(f"[GOAL] Step failed: {e}")
        return True

    # ── Autonomous personality tick (called every 30 s by agent_bridge) ───────

    def autonomous_tick(self):
        if not self.minecraft_agent:
            return

        # Execute pending goal step first
        if self._goal_steps:
            self._execute_next_goal_step()
            return

        # Read from PersonalityTraits (curiosity/boredom/aggression/affection)
        aggression = self._emotion("aggression", 20.0)
        affection  = self._emotion("affection",  50.0)
        curiosity  = self._emotion("curiosity",  50.0)
        boredom    = self._emotion("boredom",    40.0)

        logger.info(f"[AUTO] tick — agg={aggression:.0f} aff={affection:.0f} cur={curiosity:.0f} bore={boredom:.0f}")

        # Let PersonalityTraits update itself (handles its own decay/drift)
        if self.traits is not None:
            try:
                # idle=False since we're actively ticking
                self.traits.update({"idle": not bool(self._goal_steps)})
            except Exception:
                pass

        if aggression > 50 and random.random() < 0.4:
            logger.info("[AUTO] aggression → bonk")
            self.minecraft_agent.handle_intent({"intent": "MINECRAFT_LOOK",   "args": {"direction": "north"}})
            self.minecraft_agent.handle_intent({"intent": "MINECRAFT_ATTACK", "args": {"mode": "once"}})
            self._mc_chat(random.choice(["Hey!", "Don't ignore me!", "*bonk*", "Pay attention!"]))
            self._set_emotion("aggression", aggression - 20)
            return

        if affection < 20 and random.random() < 0.25:
            logger.info("[AUTO] low affection → nudge")
            self.minecraft_agent.handle_intent({"intent": "MINECRAFT_LOOK", "args": {"direction": "north"}})
            self.minecraft_agent.handle_intent({"intent": "MINECRAFT_MOVE", "args": {"direction": "forward"}})
            self._mc_chat(random.choice(["...hi.", "*nudges you*", "pets pls", "notice me"]))
            return

        if affection > 75 and random.random() < 0.15:
            logger.info("[AUTO] high affection → gift")
            self.minecraft_agent.handle_intent({"intent": "MINECRAFT_DROP", "args": {"what": "mainhand"}})
            self._mc_chat(random.choice(["I got you something!", "Here, take it!", ":3"]))
            return

        if curiosity > 55 and random.random() < 0.35:
            direction = random.choice(["forward", "backward", "left", "right"])
            logger.info(f"[AUTO] curiosity → roam {direction}")
            # Set a short explore goal instead of raw move
            self.set_goal(f"explore by walking {direction} for a bit then stopping")
            self._set_emotion("curiosity", curiosity - 15)
            if random.random() < 0.4:
                self._mc_chat(random.choice(["Ooh what's over here?", "*sniffs around*", "exploring!"]))
            return

        if boredom > 65 and random.random() < 0.3:
            logger.info("[AUTO] boredom → sit")
            self.minecraft_agent.handle_intent({"intent": "MINECRAFT_SIT", "args": {}})
            self._mc_chat(random.choice(["I'm bored...", "*stares at you*", "do SOMETHING", "zzz"]))
            self._set_emotion("boredom", boredom - 20)
            return

        # Idle look-around
        if random.random() < 0.15:
            self.minecraft_agent.handle_intent({
                "intent": "MINECRAFT_LOOK",
                "args": {"direction": random.choice(["north", "south", "east", "west"])}
            })

    # ── Message sending ───────────────────────────────────────────────────────

    def _mc_chat(self, message: str):
        if not self.minecraft_agent:
            return
        self.minecraft_agent.handle_intent({
            "intent": "MINECRAFT_CHAT",
            "args": {"message": message.strip()[:80]}
        })

    # ── Prompt loader ─────────────────────────────────────────────────────────

    def _load_prompt(self, path: str, fallback: str = "") -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return fallback

    # ── Pre-classifier ────────────────────────────────────────────────────────

    def _classify_direct(self, text: str) -> Optional[dict]:
        lower = text.lower()
        for pattern, intent in _DIRECT_INTENTS:
            if re.search(pattern, lower):
                logger.info(f"[PRE-CLASSIFY] {intent['intent']}")
                return intent
        return None

    # ── STT handlers ─────────────────────────────────────────────────────────

    def _handle_desktop_stt(self, text: str):
        if not self.llm:
            return
        try:
            personality = self._load_prompt("llm/prompts/personality.txt", "You are a helpful desktop assistant.")
            reasoning   = self._load_prompt("llm/prompts/reasoning.txt",   "Analyze input and return JSON intent.")
            resp_text = self.llm.chat([
                {"role": "system", "content": personality},
                {"role": "system", "content": reasoning},
                {"role": "user",   "content": text},
            ])
            intent = parse_intent(resp_text)
        except Exception:
            logger.exception("Desktop STT failed")
            intent = None
        if intent:
            if intent.get("intent") == "DONE":
                self.taskDone = True
            else:
                self.execute(intent)
                self.taskDone = False

    def _handle_minecraft_stt(self, text: str):
        if not self.minecraft_agent:
            return

        # 1. Pre-classifier — no LLM needed for obvious movement commands
        direct = self._classify_direct(text)
        if direct:
            self.minecraft_agent.handle_intent(direct)
            return

        # 2. Check for goal-setting phrases
        goal_match = re.search(r'\b(go|explore|find|get|build|mine|farm|collect)\b', text.lower())
        if goal_match and self.llm:
            self.set_goal(text)
            self._mc_chat(f"On it! Goal: {text[:60]}")
            return

        # 3. LLM for everything else
        if not self.llm:
            logger.warning("No LLM available for MC chat")
            return

        mc_prompt = self._load_prompt(
            "llm/prompts/minecraft_system_prompt.txt",
            'You are PetBot in Minecraft. Output ONLY raw JSON.\n'
            '{"intent":"MINECRAFT_CHAT","args":{"message":"reply here"}}'
        )
        ctx = ""
        try:
            ctx_str = self.minecraft_agent.build_context_string()
            if ctx_str and "No context" not in ctx_str:
                ctx = f"\nWORLD STATE:\n{ctx_str}\n"
        except Exception:
            pass

        user_msg = (
            f"{text}\n\n"
            f"Reply with ONLY a JSON object. Keep message ≤80 chars.\n"
            f'Example: {{"intent":"MINECRAFT_CHAT","args":{{"message":"Hi!"}}}}'
        )

        resp_text = ""
        try:
            resp_text = self.llm.chat([
                {"role": "system", "content": mc_prompt + ctx},
                {"role": "user",   "content": user_msg},
            ])
            logger.info(f"[MC LLM] raw: {repr(resp_text[:200])}")
            intent = parse_intent(resp_text)
            logger.info(f"[MC LLM] parsed: {intent}")
        except Exception:
            logger.exception("MC STT LLM call failed")
            intent = None

        if not intent:
            # Fallback: strip markdown, send whatever text came back
            if resp_text:
                cleaned = re.sub(r'[`*#\[\]{}\n]', ' ', resp_text)
                cleaned = re.sub(r'\s+', ' ', cleaned).strip()[:80]
                if cleaned:
                    self._mc_chat(cleaned)
            return

        # Cap chat length
        if intent.get("intent") == "MINECRAFT_CHAT":
            msg = intent.get("args", {}).get("message", "")
            intent["args"]["message"] = msg[:80]

        intent_name = intent.get("intent", "")
        if intent_name.startswith("MINECRAFT_"):
            self.minecraft_agent.handle_intent(intent)
        elif intent_name == "DONE":
            self.taskDone = True

    # ── Event dispatcher ──────────────────────────────────────────────────────

    def handle(self, event):
        etype = event.get("type")
        if etype == "VISION_SNAPSHOT":
            path = event.get("path")
            summary = self.vision(path)
            if self.memory:
                try: self.memory.add("vision", summary)
                except Exception: pass
            if self.llm:
                try: intent = self.llm.decide(summary)
                except Exception: intent = None
                if intent: self.execute(intent)

        elif etype == "STT_COMMAND":
            text = event.get("text", "")
            if self._is_minecraft_active() and self.minecraft_agent:
                self._handle_minecraft_stt(text)
            else:
                self._handle_desktop_stt(text)

        elif etype == "MINECRAFT_COMMAND":
            if self.minecraft_agent:
                self.minecraft_agent.handle_intent(event.get("intent", {}))

    # ── Misc actions ──────────────────────────────────────────────────────────

    def take_screenshot(self):
        path = None
        try:
            img = pyautogui.screenshot()
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                path = tmp.name; img.save(path)
            self.handle({"type": "VISION_SNAPSHOT", "path": path, "source": "desktop"})
        finally:
            if path and os.path.exists(path):
                try: os.remove(path)
                except OSError: pass

    def searchWeb(self, query):
        if not query: return []
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=5):
                    results.append({"title": r.get("title",""), "snippet": r.get("body",""), "url": r.get("href","")})
        except Exception: logger.exception("searchWeb failed")
        return results

    def openApp(self, app: str) -> bool:
        if not app: return False
        app = app.strip()
        candidate = shutil.which(app) or shutil.which(app.lower()) or shutil.which(app+'.exe')
        if candidate:
            try: subprocess.Popen([candidate]); return True
            except Exception: pass
        try:
            if sys.platform.startswith('win'):
                try: subprocess.Popen([app+'.exe']); return True
                except FileNotFoundError:
                    try: os.startfile(app); return True
                    except Exception: pass
            elif sys.platform == 'darwin':
                subprocess.Popen(['open','-a',app]); return True
            else:
                subprocess.Popen([app]); return True
        except Exception: pass
        return False

    def vision(self, path):
        try: return LLMClient(model_name="llava").chat([{"role":"user","content":"Describe this screenshot"}])
        except Exception: return "(vision unavailable)"

    def click(self, x, y):
        try: pyautogui.click(x, y); return True
        except Exception: return False

    def type_text(self, text):
        try: pyautogui.typewrite(text); return True
        except Exception: return False

    def move_mouse(self, x, y):
        try: pyautogui.moveTo(x, y); return True
        except Exception: return False

    def verify(self): pass

    def execute(self, intent):
        if not intent or "intent" not in intent: return None
        name = intent.get("intent")
        args = intent.get("args", {}) or {}
        if name.startswith("MINECRAFT_"):
            if self.minecraft_agent: return self.minecraft_agent.handle_intent(intent)
            return None
        if name == "TAKE_SCREENSHOT": return self.take_screenshot()
        if name == "OPEN_APP":        return self.openApp(args.get("app"))
        if name == "SEARCH_WEB":      return self.searchWeb(args.get("query"))
        if name == "CLICK"      and self.verify() is True: return self.click(args.get("x"), args.get("y"))
        if name == "TYPE"       and self.verify() is True: return self.type_text(args.get("text"))
        if name == "MOVE_MOUSE" and self.verify() is True: return self.move_mouse(args.get("x"), args.get("y"))
        if name == "DONE": self.taskDone = True; return True
        logger.warning("Unknown intent: %s", name)
        return None