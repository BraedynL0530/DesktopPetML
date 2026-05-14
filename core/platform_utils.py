"""
core/platform_utils.py
Cross-platform helpers for window-title detection and process inspection.
Works on Windows, Linux (X11), and macOS.
"""

import os
import sys
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional psutil import
# ---------------------------------------------------------------------------
try:
    import psutil as _psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _psutil = None
    _PSUTIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Minecraft process keywords
# ---------------------------------------------------------------------------
_MC_PROCESS_NAMES = frozenset({"java", "javaw", "minecraft", "minecraft launcher"})
_MC_CMDLINE_KEYS  = frozenset({
    "minecraft", "net.minecraft", "fabric-loader", "fabricloader",
    "forge", "quiltmc", "optifine",
})
_MC_WINDOW_KEYWORDS = frozenset({"minecraft", "java edition", "fabric", "forge"})


# ---------------------------------------------------------------------------
# Active-window title
# ---------------------------------------------------------------------------

def get_active_window_title() -> Optional[str]:
    """
    Return the title of the currently focused window.

    Platform support:
    - Windows: uses pygetwindow (already a dependency)
    - Linux (X11): tries xdotool, falls back to python-wnck via GObject
    - macOS: uses osascript
    Returns None on any failure.
    """
    try:
        if sys.platform == "win32":
            return _get_title_windows()
        elif sys.platform == "darwin":
            return _get_title_macos()
        else:
            return _get_title_linux()
    except Exception as exc:
        logger.debug("get_active_window_title error: %s", exc)
        return None


def _get_title_windows() -> Optional[str]:
    try:
        import pygetwindow as gw
        w = gw.getActiveWindow()
        return (w.title or None) if w else None
    except Exception:
        return None


def _get_title_macos() -> Optional[str]:
    script = (
        'tell application "System Events" '
        'to get name of first application process whose frontmost is true'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _get_title_linux() -> Optional[str]:
    # 1) xdotool (most common)
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 2) python-wnck via GObject introspection
    try:
        import gi  # type: ignore
        gi.require_version("Wnck", "3.0")
        from gi.repository import Wnck  # type: ignore
        screen = Wnck.Screen.get_default()
        if screen:
            screen.force_update()
            window = screen.get_active_window()
            return window.get_name() if window else None
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Minecraft process detection (cross-platform via psutil)
# ---------------------------------------------------------------------------

def is_minecraft_running() -> bool:
    """
    Return True if a Minecraft Java process is detected.
    Uses psutil when available; falls back to window-title heuristic.
    """
    if _PSUTIL_AVAILABLE:
        return _mc_via_psutil()

    # psutil not available — fall back to window-title check
    title = get_active_window_title()
    if title:
        tl = title.lower()
        return any(kw in tl for kw in _MC_WINDOW_KEYWORDS)
    return False


def _mc_via_psutil() -> bool:
    try:
        for proc in _psutil.process_iter(["name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if not any(mc in name for mc in _MC_PROCESS_NAMES):
                    # Quick-path: skip non-java/minecraft-named processes
                    if "java" not in name:
                        continue
                cmdline_parts = proc.info.get("cmdline") or []
                cmdline = " ".join(cmdline_parts).lower()
                if any(kw in cmdline for kw in _MC_CMDLINE_KEYS):
                    return True
            except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                continue
    except Exception as exc:
        logger.debug("psutil MC scan failed: %s", exc)
    return False


# ---------------------------------------------------------------------------
# XDG / platform data directories
# ---------------------------------------------------------------------------

def get_data_dir(app_name: str = "DesktopPetML") -> str:
    """
    Return the appropriate data directory for the current platform.

    - Linux:   $XDG_DATA_HOME/<app_name>   (~/.local/share/<app_name>)
    - macOS:   ~/Library/Application Support/<app_name>
    - Windows: %APPDATA%/<app_name>
    """
    if sys.platform.startswith("linux"):
        base = os.environ.get(
            "XDG_DATA_HOME",
            os.path.join(os.path.expanduser("~"), ".local", "share"),
        )
    elif sys.platform == "darwin":
        base = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support"
        )
    else:
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(base, app_name)


def get_config_dir(app_name: str = "DesktopPetML") -> str:
    """
    Return the appropriate config directory for the current platform.

    - Linux:   $XDG_CONFIG_HOME/<app_name>  (~/.config/<app_name>)
    - macOS:   ~/Library/Application Support/<app_name>
    - Windows: %APPDATA%/<app_name>
    """
    if sys.platform.startswith("linux"):
        base = os.environ.get(
            "XDG_CONFIG_HOME",
            os.path.join(os.path.expanduser("~"), ".config"),
        )
    elif sys.platform == "darwin":
        base = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support"
        )
    else:
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(base, app_name)


def get_cache_dir(app_name: str = "DesktopPetML") -> str:
    """
    Return the appropriate cache directory for the current platform.

    - Linux:   $XDG_CACHE_HOME/<app_name>  (~/.cache/<app_name>)
    - macOS:   ~/Library/Caches/<app_name>
    - Windows: %LOCALAPPDATA%/<app_name>\\Cache
    """
    if sys.platform.startswith("linux"):
        base = os.environ.get(
            "XDG_CACHE_HOME",
            os.path.join(os.path.expanduser("~"), ".cache"),
        )
    elif sys.platform == "darwin":
        base = os.path.join(
            os.path.expanduser("~"), "Library", "Caches"
        )
    else:
        base = os.environ.get(
            "LOCALAPPDATA",
            os.path.join(os.path.expanduser("~"), "AppData", "Local"),
        )
        return os.path.join(base, app_name, "Cache")
    return os.path.join(base, app_name)
