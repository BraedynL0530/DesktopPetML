INTENTS = {
    "OPEN_APP": {
        "description": "Open an application by name",
        "required_args": ["app"]
    },
    "TAKE_SCREENSHOT": {
        "description": "Take a screenshot of the desktop",
        "required_args": []
    },
    "SEARCH_WEB": {
        "description": "Search the web for a query",
        "required_args": ["query"]

    },
    "SEND_MESSAGE": {
        "description": "Send a message to user / chat",
        "required_args": ["text"]
    },
    "CLICK": {
        "description": "Click on screen coordinates",
        "required_args": ["x", "y"]
    },
    "TYPE": {
        "description": "Type text",
        "required_args": ["text"]
    },
    "MOVE_MOUSE": {
        "description": "Move mouse to position",
        "required_args": ["x", "y"]
    },
    "DONE": {
        "description": "ends Loop",
        "required_args": []
    }
    # ...
}
MINECRAFT_INTENTS = {
    "MINECRAFT_MINE": {
        "description": "Mine a block in Minecraft",
        "required_args": ["x", "y", "z"]
    },
    "MINECRAFT_PLACE": {
        "description": "Place a block in Minecraft",
        "required_args": ["x", "y", "z", "block_type"]
    },
    "MINECRAFT_MOVE": {
        "description": "Move fake player",
        "required_args": ["direction"],
        "optional_args": ["distance"]
    },
    "MINECRAFT_SIT": {
        "description": "Sit on furniture using JustSit",
        "required_args": ["furniture_id"]
    },
    "MINECRAFT_INTERACT": {
        "description": "Interact (right-click) with a block",
        "required_args": ["x", "y", "z"]
    },
    "MINECRAFT_FARM": {
        "description": "Automated farming sequence",
        "required_args": ["crop_type"],
        "optional_args": ["rows"]
    },
    "MINECRAFT_BUILD": {
        "description": "Build a structure",
        "required_args": ["structure", "x", "y", "z"]
    },
    "MINECRAFT_SEARCH_ITEM": {
        "description": "Search for item in JEI",
        "required_args": ["item_name"]
    },
    "MINECRAFT_CHAT": {
        "description": "Send message in Minecraft chat",
        "required_args": ["message"]
    },
}

# Merge into main INTENTS
INTENTS.update(MINECRAFT_INTENTS)