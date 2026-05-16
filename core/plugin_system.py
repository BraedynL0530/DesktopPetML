from typing import Callable, Dict, Optional, Tuple


class PluginManager:
    def __init__(self, enabled_plugins=None, context: Optional[Dict] = None):
        self._context = context or {}
        self._plugins = []
        enabled = set((enabled_plugins or []))

        if "obsidian" in enabled:
            from core.plugins.obsidian_plugin import ObsidianPlugin
            self._plugins.append(ObsidianPlugin(self._context))
        if "tui" in enabled:
            from core.plugins.tui_plugin import TUIPlugin
            self._plugins.append(TUIPlugin(self._context))

    def handle_command(self, text: str) -> Tuple[bool, Optional[str]]:
        for plugin in self._plugins:
            try:
                handled, response = plugin.handle_command(text)
                if handled:
                    return True, response
            except Exception as e:
                return True, f"Plugin '{plugin.name}' error: {e}"
        return False, None

    @property
    def loaded_plugin_names(self):
        return [p.name for p in self._plugins]
