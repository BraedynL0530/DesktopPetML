"""
minecraft/minecraft_agent.py
Translates LLM intents into MinecraftBridge calls.
"""
import json
import logging
from minecraft.minecraft_bridge import MinecraftBridge

logger = logging.getLogger(__name__)


class MinecraftAgent:
    def __init__(self, mc_bridge: MinecraftBridge):
        self.mc = mc_bridge

    def build_context_string(self) -> str:
        """Format latest world state for the LLM system prompt."""
        ctx = self.mc.get_context()
        if not ctx:
            return "No context yet — PetBot may still be loading."
        return json.dumps(ctx, indent=2)

    def handle_intent(self, intent: dict) -> bool:
        name = intent.get("intent", "")
        args = intent.get("args", {})

        handlers = {
            "MINECRAFT_MOVE":        self._move,
            "MINECRAFT_STOP":        self._stop,
            "MINECRAFT_JUMP":        self._jump,
            "MINECRAFT_SNEAK":       self._sneak,
            "MINECRAFT_SPRINT":      self._sprint,
            "MINECRAFT_LOOK":        self._look,
            "MINECRAFT_TURN":        self._turn,
            "MINECRAFT_HOTBAR":      self._hotbar,
            "MINECRAFT_DROP":        self._drop,
            "MINECRAFT_USE":         self._use,
            "MINECRAFT_ATTACK":      self._attack,
            "MINECRAFT_SIT":         self._sit,
            "MINECRAFT_CHAT":        self._chat,
            "MINECRAFT_MINE":        self._mine,
            "MINECRAFT_PLACE":       self._place,
            "MINECRAFT_INTERACT":    self._interact,
            "MINECRAFT_SEARCH_ITEM": self._search_item,
        }

        handler = handlers.get(name)
        if not handler:
            logger.warning(f"Unknown intent: {name}")
            return False
        try:
            return handler(**args)
        except Exception as e:
            logger.error(f"Intent {name} failed: {e}", exc_info=True)
            return False

    # ── Movement ──────────────────────────────────────────────
    def _move(self, direction="forward", **kw):
        # Normalise: agent might say 'back', Carpet needs 'backward'
        if direction == "back":
            direction = "backward"
        return self.mc.move(direction)

    def _stop(self, **kw):
        return self.mc.stop()

    def _jump(self, **kw):
        return self.mc.jump()

    def _sneak(self, enable=True, **kw):
        return self.mc.sneak(bool(enable))

    def _sprint(self, enable=True, **kw):
        return self.mc.sprint(bool(enable))

    # ── Looking ───────────────────────────────────────────────
    def _look(self, direction=None, yaw=None, pitch=None, **kw):
        if direction:
            return self.mc.look_direction(direction)
        if yaw is not None and pitch is not None:
            return self.mc.look_rotation(float(yaw), float(pitch))
        return False

    def _turn(self, direction="left", **kw):
        return self.mc.turn(direction)

    # ── Inventory ─────────────────────────────────────────────
    def _hotbar(self, slot=0, **kw):
        return self.mc.hotbar(int(slot))

    def _drop(self, what="mainhand", **kw):
        return self.mc.drop(what)

    # ── Actions ───────────────────────────────────────────────
    def _use(self, mode="once", **kw):
        return self.mc.use(mode)

    def _attack(self, mode="once", **kw):
        return self.mc.attack(mode)

    def _sit(self, **kw):
        return self.mc.sit()

    def _chat(self, message="", **kw):
        return self.mc.chat(str(message))

    # ── Blocks ────────────────────────────────────────────────
    def _mine(self, x=0, y=0, z=0, **kw):
        return self.mc.mine_block(int(x), int(y), int(z))

    def _place(self, x=0, y=0, z=0, block_type="minecraft:stone", **kw):
        return self.mc.place_block(int(x), int(y), int(z), block_type)

    def _interact(self, x=0, y=0, z=0, **kw):
        return self.mc.interact_block(int(x), int(y), int(z))

    def _search_item(self, item_name="", **kw):
        return self.mc.search_jei(item_name)