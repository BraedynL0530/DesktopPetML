"""
core/minecraft_agent.py
Agent for handling Minecraft-specific intents.
Communicates with in-game Scarplet scripts via HTTP (no RCON required).
"""
import logging
from minecraft.minecraft_bridge import MinecraftBridge

logger = logging.getLogger(__name__)


class MinecraftAgent:
    """Handles Minecraft-specific commands dispatched from the LLM."""

    def __init__(self, mc_bridge: MinecraftBridge):
        self.mc = mc_bridge
        self.fake_player_name = "PetBot"

    # ------------------------------------------------------------------ #
    # Intent router                                                        #
    # ------------------------------------------------------------------ #

    def handle_intent(self, intent: dict) -> bool:
        """
        Route an LLM-generated intent dict to the right handler.

        Example intent:
            {"intent": "MINECRAFT_MINE", "args": {"x": 100, "y": 64, "z": 200}}
        """
        intent_name = intent.get("intent")
        args = intent.get("args", {})

        handlers = {
            "MINECRAFT_MINE":        self.mine,
            "MINECRAFT_PLACE":       self.place,
            "MINECRAFT_MOVE":        self.move,
            "MINECRAFT_SIT":         self.sit,
            "MINECRAFT_INTERACT":    self.interact,
            "MINECRAFT_FARM":        self.farm,
            "MINECRAFT_BUILD":       self.build,
            "MINECRAFT_SEARCH_ITEM": self.search_item,
            "MINECRAFT_CHAT":        self.chat_in_game,
        }

        handler = handlers.get(intent_name)
        if not handler:
            logger.warning(f"Unknown intent: {intent_name}")
            return False

        try:
            return handler(**args)
        except Exception as e:
            logger.error(f"Intent {intent_name} failed: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Core actions                                                         #
    # ------------------------------------------------------------------ #

    def mine(self, x: int, y: int, z: int, **kwargs) -> bool:
        logger.info(f"Mining block at {x}, {y}, {z}")
        return self.mc.mine_block(x, y, z)

    def place(self, x: int, y: int, z: int, block_type: str, **kwargs) -> bool:
        logger.info(f"Placing {block_type} at {x}, {y}, {z}")
        return self.mc.place_block(x, y, z, block_type)

    def move(self, direction: str, distance: float = 5.0, **kwargs) -> bool:
        logger.info(f"Moving {direction} × {distance}")
        return self.mc.move_player(direction, distance)

    def sit(self, furniture_id: str, **kwargs) -> bool:
        logger.info(f"Sitting on {furniture_id}")
        return self.mc.sit_on_furniture(furniture_id)

    def interact(self, x: int, y: int, z: int, **kwargs) -> bool:
        logger.info(f"Interacting with block at {x}, {y}, {z}")
        return self.mc.click_block(x, y, z)

    # ------------------------------------------------------------------ #
    # Complex behaviours                                                   #
    # ------------------------------------------------------------------ #

    def farm(self, crop_type: str = "wheat", rows: int = 3, **kwargs) -> bool:
        """
        Trigger the petbot_farm.sc script in-game.

        Args:
            crop_type: "wheat" | "carrots" | "potatoes" | "beetroot"
            rows:      number of rows to harvest/replant
        """
        logger.info(f"Starting farm: {rows} rows of {crop_type}")
        # Pass crop params as extra context via a raw command so Scarplet
        # can read them, then kick off the script.
        self.mc.execute_command(
            f"script run global FARM_CROP = '{crop_type}'; global FARM_ROWS = {rows};"
        )
        return self.mc.script_fake_player("farming", self.fake_player_name)

    def build(self, structure: str, x: int, y: int, z: int, **kwargs) -> bool:
        """
        Build a pre-defined structure using petbot_build.sc.

        Args:
            structure: "house" | "tower" | "platform"
            x, y, z:  base coordinates
        """
        logger.info(f"Building {structure} at {x}, {y}, {z}")
        self.mc.execute_command(
            f"script run global BUILD_X={x}; global BUILD_Y={y}; global BUILD_Z={z};"
        )
        return self.mc.script_fake_player(f"build_{structure}", self.fake_player_name)

    def search_item(self, item_name: str, **kwargs) -> list:
        logger.info(f"JEI search: {item_name}")
        return self.mc.search_jei(item_name)

    def chat_in_game(self, message: str, **kwargs) -> bool:
        logger.info(f"In-game chat: {message}")
        return bool(self.mc.execute_command(f"say {message}"))