
import pygetwindow as gw
from typing import Optional


class WindowsIntegration:
    """
    Handles Windows-specific operations
    - Get active window
    - Take screenshots (for vision model)
    - Execute commands
    """

    def __init__(self):
        pass

    def get_active_app(self) -> Optional[str]:
        """Get currently active window title"""
        fg = gw.getActiveWindow()
        if fg and fg.title:
            return fg.title
        return None

    def take_screenshot(self):
        """
        TODO: Implement screenshot capture
        This is where I will integrate vision model

        Capture screen, Send to vision LLM, Get description/context, Use that instead of window title(future agent stuff instead of just trees)
        """
        # Placeholder for your vision implementation
        raise NotImplementedError("Add vision model integration here")

