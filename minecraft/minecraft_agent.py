"""
core/minecraft_agent.py
Agent for handling Minecraft-specific intents
Extends the main agents class
"""
import logging
from minecraft_bridge import MinecraftBridge

logger = logging.getLogger(__name__)


class MinecraftAgent:
    """Handles Minecraft-specific commands from the LLM"""

    def __init__(self, mc_bridge: MinecraftBridge):
        self.mc = mc_bridge
        self.fake_player_name = "PetBot"
        self.last_position = None

    def handle_intent(self, intent: dict) -> bool:
        """
        Route Minecraft intents to appropriate handlers

        Example intent:
        {
            "intent": "MINECRAFT_MINE",
            "args": {
                "x": 100,
                "y": 64,
                "z": 200,
            }
        }
        """
        intent_name = intent.get("intent")
        args = intent.get("args", {})

        handlers = {
            "MINECRAFT_MINE": self.mine,
            "MINECRAFT_PLACE": self.place,
            "MINECRAFT_MOVE": self.move,
            "MINECRAFT_SIT": self.sit,
            "MINECRAFT_INTERACT": self.interact,
            "MINECRAFT_FARM": self.farm,
            "MINECRAFT_BUILD": self.build,
            "MINECRAFT_SEARCH_ITEM": self.search_item,
            "MINECRAFT_CHAT": self.chat_in_game,
        }

        handler = handlers.get(intent_name)
        if handler:
            try:
                result = handler(**args)
                return result
            except Exception as e:
                logger.error(f"Minecraft intent failed: {e}")
                return False

        return False

    # ========================================================================
    # CORE ACTIONS
    # ========================================================================

    def mine(self, x: int, y: int, z: int, **kwargs) -> bool:
        """Mine block at coordinates"""
        logger.info(f"Mining block at {x}, {y}, {z}")
        return self.mc.mine_block(x, y, z)

    def place(self, x: int, y: int, z: int, block_type: str, **kwargs) -> bool:
        """Place block at coordinates"""
        logger.info(f"Placing {block_type} at {x}, {y}, {z}")
        return self.mc.place_block(x, y, z, block_type)

    def move(self, direction: str, distance: float = 5.0, **kwargs) -> bool:
        """Move in direction"""
        logger.info(f"Moving {direction} by {distance} blocks")
        return self.mc.move_player(direction, distance)

    def sit(self, furniture_id: str, **kwargs) -> bool:
        """Sit on furniture (JustSit)"""
        logger.info(f"Sitting on {furniture_id}")
        return self.mc.sit_on_furniture(furniture_id)

    def interact(self, x: int, y: int, z: int, **kwargs) -> bool:
        """Interact with block (right-click)"""
        logger.info(f"Interacting with {x}, {y}, {z}")
        return self.mc.click_block(x, y, z)

    # ========================================================================
    # COMPLEX BEHAVIORS
    # ========================================================================

    def farm(self, crop_type: str = "wheat", rows: int = 3, **kwargs) -> bool:
        """
        Automated farming using Scarplet

        Args:
            crop_type: "wheat", "carrots", "potatoes", etc.
            rows: Number of rows to farm
        """
        logger.info(f"Farming {rows} rows of {crop_type}")
        script = f"""
        // Scarplet script for farming
        global crop = '{crop_type}';
        global rows = {rows};

        for(i = 0; i < rows; i++) {{
            player_move(0, 1, 0);  // Move forward
            player_mine();         // Mine crop
            player_place('{crop_type}');  // Place new seeds
        }}
        """
        return self.mc.script_fake_player("farming", self.fake_player_name)

    def build(self, structure: str, x: int, y: int, z: int, **kwargs) -> bool:
        """
        Build structure using Scarplet blueprint

        Args:
            structure: Name of pre-defined structure ("house", "tower", etc.)
            x, y, z: Base coordinates
        """
        logger.info(f"Building {structure} at {x}, {y}, {z}")
        # Would load blueprint and execute build sequence
        return self.mc.script_fake_player(f"build_{structure}", self.fake_player_name)

    def search_item(self, item_name: str, **kwargs) -> list:
        """Search JEI for item"""
        logger.info(f"Searching for {item_name}")
        return self.mc.search_jei(item_name)

    def chat_in_game(self, message: str, **kwargs) -> bool:
        """Send message to Minecraft chat"""
        logger.info(f"Chatting in game: {message}")
        return bool(self.mc.execute_command(f"say {message}"))