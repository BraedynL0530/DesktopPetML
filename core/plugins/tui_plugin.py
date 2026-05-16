class TUIPlugin:
    name = "tui"

    def __init__(self, context=None):
        self.context = context or {}

    def handle_command(self, text: str):
        cmd = (text or "").strip().lower()
        if cmd in ("cat -show", "show cat", "last command"):
            cb = self.context.get("set_cat_visible")
            if callable(cb):
                cb(True)
            return True, "PyQt cat shown."

        if cmd in ("cat -hide", "cat hide"):
            cb = self.context.get("set_cat_visible")
            if callable(cb):
                cb(False)
            return True, "PyQt cat hidden."

        return False, None
