INTENTS = {
    "OPEN_APP": {
        "description": "Open an application by name",
        "required_args": ["app"]
    },
    "TAKE_SCREENSHOT": {
        "description": "Take a screenshot of the desktop",
        "required_args": []
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
    }
    # ...
}