"""
minecraft/minecraft_agent.py
Translates LLM intents into MinecraftBridge calls.
Now with distance-based movement and personality influence.
"""
import json
import logging
import math
from minecraft.minecraft_bridge import MinecraftBridge

logger = logging.getLogger(__name__)


class MinecraftAgent:
    def __init__(self, mc_bridge: MinecraftBridge, personality_traits=None):
        self.mc = mc_bridge
        self.personality = personality_traits or {}  # Optional {curiosity, affection, aggression, boredom}
        self._movement_history = []  # Track recent movements for pathfinding

    def build_context_string(self) -> str:
        """Format latest world state for the LLM system prompt."""
        ctx = self.mc.get_context()
        if not ctx:
            return "No context yet — PetBot may still be loading."

        lines = [
            f"Position: {ctx.get('pos')}",
            f"Facing: yaw={ctx.get('yaw'):.0f}° pitch={ctx.get('pitch'):.0f}°",
            f"Holding: {ctx.get('held_main', 'empty')}",
            f"Below: {ctx.get('block_below')}",
            f"Nearby: N={ctx.get('block_north')} S={ctx.get('block_south')} E={ctx.get('block_east')} W={ctx.get('block_west')}",
        ]

        if ctx.get('move_active'):
            lines.append("⚠ Currently moving — will stop automatically")

        return "\n".join(lines)

    def handle_intent(self, intent: dict) -> bool:
        """Execute intent, returning True/False for success."""
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

    # ──────────────────────────────────────────────────────────────────────
    # MOVEMENT WITH DISTANCE TRACKING
    # ──────────────────────────────────────────────────────────────────────

    def _move(self, direction="forward", distance=None, **kw):
        """
        Move in a direction with optional distance.

        distance: can be:
          - int/float: blocks to move (1.0 = 1 block)
          - "short" = 1 block
          - "medium" = 3 blocks
          - "long" = 6 blocks
          - None = 1 block (default)
        """
        # Normalise direction
        if direction == "back":
            direction = "backward"

        # Determine distance in blocks
        if distance is None:
            blocks = 1.0
        elif isinstance(distance, (int, float)):
            blocks = float(distance)
        elif distance == "short":
            blocks = 1.0
        elif distance == "medium":
            blocks = 3.0
        elif distance == "long":
            blocks = 6.0
        else:
            blocks = 1.0

        # Influence by personality: affection affects caution
        if self.personality and self.personality.get("affection", 50) < 30:
            # Low affection = more reckless, longer moves
            blocks *= 1.2

        logger.info(f"Moving {direction} {blocks:.1f} blocks")
        self._movement_history.append({"direction": direction, "distance": blocks})

        return self.mc.move(direction, distance=blocks)

    def _stop(self, **kw):
        """Stop all movement immediately."""
        logger.info("Stopping movement")
        return self.mc.stop()

    def _jump(self, **kw):
        """Jump."""
        return self.mc.jump()

    def _sneak(self, enable=True, **kw):
        """Toggle sneaking."""
        action = "sneak" if enable else "unsneak"
        return self.mc.sneak(bool(enable))

    def _sprint(self, enable=True, **kw):
        """Toggle sprinting."""
        return self.mc.sprint(bool(enable))

    # ──────────────────────────────────────────────────────────────────────
    # LOOKING & TURNING
    # ──────────────────────────────────────────────────────────────────────

    def _look(self, direction=None, yaw=None, pitch=None, **kw):
        """Look in a direction or at absolute yaw/pitch."""
        if direction:
            return self.mc.look_direction(direction)
        if yaw is not None and pitch is not None:
            return self.mc.look_rotation(float(yaw), float(pitch))
        return False

    def _turn(self, direction="left", **kw):
        """Turn left/right/back."""
        return self.mc.turn(direction)

    # ──────────────────────────────────────────────────────────────────────
    # INVENTORY
    # ──────────────────────────────────────────────────────────────────────

    def _hotbar(self, slot=0, **kw):
        """Select hotbar slot (0-8)."""
        slot = int(slot) % 9
        return self.mc.hotbar(slot)

    def _drop(self, what="mainhand", **kw):
        """Drop item from hand or slot."""
        return self.mc.drop(what)

    # ──────────────────────────────────────────────────────────────────────
    # ACTIONS
    # ──────────────────────────────────────────────────────────────────────

    def _use(self, mode="once", **kw):
        """Right-click (use) action."""
        return self.mc.use(mode)

    def _attack(self, mode="once", **kw):
        """Left-click (attack) action."""
        return self.mc.attack(mode)

    def _sit(self, **kw):
        """Sit down (requires JustSit mod)."""
        return self.mc.sit()

    def _chat(self, message="", **kw):
        """Say something in chat."""
        return self.mc.chat(str(message)[:80])

    # ──────────────────────────────────────────────────────────────────────
    # BLOCKS
    # ──────────────────────────────────────────────────────────────────────

    def _mine(self, x=0, y=0, z=0, **kw):
        """Mine block at coordinates."""
        return self.mc.mine_block(int(x), int(y), int(z))

    def _place(self, x=0, y=0, z=0, block_type="minecraft:stone", **kw):
        """Place block at coordinates."""
        return self.mc.place_block(int(x), int(y), int(z), block_type)

    def _interact(self, x=0, y=0, z=0, **kw):
        """Interact (right-click) with block."""
        return self.mc.interact_block(int(x), int(y), int(z))

    def _search_item(self, item_name="", **kw):
        """Search for item in JEI (Just Enough Items)."""
        return self.mc.search_jei(item_name)