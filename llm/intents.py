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