"""
core/config.py
Performance and feature configuration for DesktopPetML.

All settings can be overridden via environment variables or by editing the
values directly in this file.  Environment variables take precedence.

Example (Linux/macOS):
    DPETML_QUIET=1 DPETML_POLL_IDLE=15 python ui/pet.py

Example (Windows PowerShell):
    $env:DPETML_QUIET="1"; python ui/pet.py
"""

import os

# ---------------------------------------------------------------------------
# Poll intervals (seconds)
# How often the background worker checks things while the user is …
# ---------------------------------------------------------------------------

# … idle (no app activity detected)
POLL_INTERVAL_IDLE = float(os.environ.get("DPETML_POLL_IDLE", "10.0"))

# … actively using a non-game app
POLL_INTERVAL_ACTIVE = float(os.environ.get("DPETML_POLL_ACTIVE", "5.0"))

# … with Minecraft detected / bridge active
POLL_INTERVAL_MINECRAFT = float(os.environ.get("DPETML_POLL_MC", "2.0"))

# How often to re-check whether Minecraft is running (seconds).
# Kept longer so psutil scan doesn't happen on every iteration.
MC_DETECT_INTERVAL = float(os.environ.get("DPETML_MC_DETECT", "15.0"))

# ---------------------------------------------------------------------------
# Autonomous-tick interval (seconds)
# How often the AI bot performs an unsolicited in-game action
# ---------------------------------------------------------------------------
AUTONOMOUS_INTERVAL_DEFAULT = float(os.environ.get("DPETML_AUTO_DEFAULT", "30.0"))
AUTONOMOUS_INTERVAL_MINECRAFT = float(os.environ.get("DPETML_AUTO_MC", "15.0"))

# ---------------------------------------------------------------------------
# Mode flags
# ---------------------------------------------------------------------------

# quiet_mode: reduce all background activity (longer intervals, lower FPS)
QUIET_MODE = os.environ.get("DPETML_QUIET", "0").lower() in ("1", "true", "yes")

# minecraft_mode: force MC-specific behaviours regardless of auto-detection
MINECRAFT_MODE = os.environ.get("DPETML_MC_MODE", "0").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Messenger
# ---------------------------------------------------------------------------

# Minimum seconds between spontaneous chat-bubble messages
MESSENGER_INTERVAL = int(os.environ.get("DPETML_MSG_INTERVAL", "120"))

# ---------------------------------------------------------------------------
# Memory limits
# ---------------------------------------------------------------------------

# Maximum number of events kept in ShortTermMemory (deque cap)
SHORT_MEMORY_MAX_ITEMS = int(os.environ.get("DPETML_MEM_MAX", "200"))

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

# Timeout for Ollama chat calls (seconds).  Set to 0 to disable timeout.
LLM_TIMEOUT = float(os.environ.get("DPETML_LLM_TIMEOUT", "30.0"))
LLM_PROVIDER = os.environ.get("DPETML_LLM_PROVIDER", "gemini").strip().lower()
LLM_MODEL = os.environ.get("DPETML_LLM_MODEL", "").strip()
GEMINI_API_KEY = os.environ.get("DPETML_GEMINI_API_KEY", "").strip()

# Plugin system
DEFAULT_ENABLED_PLUGINS = "obsidian,tui"
_plugins_raw = os.environ.get("DPETML_ENABLED_PLUGINS", DEFAULT_ENABLED_PLUGINS).split(",")
ENABLED_PLUGINS = []
for _plugin in _plugins_raw:
    _clean = _plugin.strip().lower()
    if _clean:
        ENABLED_PLUGINS.append(_clean)

# MCP / Obsidian
MCP_OBSIDIAN_HOST = os.environ.get("DPETML_MCP_HOST", "127.0.0.1").strip()
MCP_OBSIDIAN_PORT = int(os.environ.get("DPETML_MCP_PORT", "0"))
MCP_OBSIDIAN_COMMAND = os.environ.get("DPETML_MCP_COMMAND", "").strip()
MCP_TIMEOUT = float(os.environ.get("DPETML_MCP_TIMEOUT", "10.0"))

# ---------------------------------------------------------------------------
# Optional int8 / reduced-precision quantization
#
# scikit-learn's IsolationForest does not support true int8 quantization.
# When this flag is enabled the tracker converts numpy feature arrays to
# float32 (halving memory vs float64) before training and inference.
# Full ONNX / torch int8 quantization is reserved for future work when
# the model stack supports it.
# ---------------------------------------------------------------------------
ENABLE_INT8_QUANTIZATION = os.environ.get("DPETML_INT8", "0").lower() in (
    "1", "true", "yes"
)

# ---------------------------------------------------------------------------
# Browser / app tab rate-limit
# Minimum seconds that must elapse between successive OPEN_APP / OPEN_TAB
# actions triggered autonomously (voice-command actions are not throttled).
# ---------------------------------------------------------------------------
TAB_RATE_LIMIT_SECONDS = float(os.environ.get("DPETML_TAB_RATE", "30.0"))

# ---------------------------------------------------------------------------
# Convenience: apply quiet-mode multipliers to all intervals
# ---------------------------------------------------------------------------
if QUIET_MODE:
    POLL_INTERVAL_IDLE *= 2
    POLL_INTERVAL_ACTIVE *= 2
    POLL_INTERVAL_MINECRAFT *= 2
    AUTONOMOUS_INTERVAL_DEFAULT *= 2
    AUTONOMOUS_INTERVAL_MINECRAFT *= 2
    MESSENGER_INTERVAL = max(MESSENGER_INTERVAL, 180)
