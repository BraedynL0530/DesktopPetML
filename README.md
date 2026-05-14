#  **DESKTOP PET w/ MINECRAFT & MACHINE LEARNING** 🤖🎮
A smart desktop companion that learns your computer habits, integrates with Minecraft, and reacts to your behavior!


## 📦 **Installation**
1. Install Ollama: https://ollama.ai
2. Pull model: `ollama pull gemma2:2b` (or gemma3:4b)
3. Clone repo and install deps: `pip install -r requirements.txt`
4. For Minecraft: Install Fabric + Carpet mod on your server

### 🐧 Linux Notes
- Window-title detection requires **xdotool**: `sudo apt install xdotool`
- Minecraft process detection uses **psutil** (included in requirements)
- Config and model files are stored in XDG directories:
  - Data: `~/.local/share/DesktopPetML/`
  - Config: `~/.config/DesktopPetML/`
  - Cache: `~/.cache/DesktopPetML/`
- The `keyboard` library for global hotkeys requires root on Linux; without it the hotkey is disabled but the pet still runs normally
- Optional DE integration: `pip install pystray notify2`

## 🎯 **Quick Start**
```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Start skin server (if using Minecraft)
cd your_project
python serve_skins.py

# Terminal 3: Run the pet
python ui/pet.py
```


## ⚡ **Performance Modes & Configuration**

All settings can be overridden via environment variables **or** by editing `core/config.py` directly.

| Environment variable | Default | Description |
|---|---|---|
| `DPETML_QUIET` | `0` | Enable quiet mode — doubles all intervals, reduces background activity |
| `DPETML_MC_MODE` | `0` | Force Minecraft mode on regardless of auto-detection |
| `DPETML_POLL_IDLE` | `10.0` | Worker poll interval when idle (seconds) |
| `DPETML_POLL_ACTIVE` | `5.0` | Worker poll interval when app activity is detected (seconds) |
| `DPETML_POLL_MC` | `2.0` | Worker poll interval while Minecraft is running (seconds) |
| `DPETML_MC_DETECT` | `15.0` | How often to re-scan for a Minecraft process (seconds) |
| `DPETML_AUTO_DEFAULT` | `30.0` | Autonomous in-game action interval — default (seconds) |
| `DPETML_AUTO_MC` | `15.0` | Autonomous action interval while Minecraft is active (seconds) |
| `DPETML_MSG_INTERVAL` | `120` | Minimum seconds between spontaneous chat-bubble messages |
| `DPETML_MEM_MAX` | `200` | Max events kept in short-term memory (prevents unbounded growth) |
| `DPETML_LLM_TIMEOUT` | `30.0` | Timeout for Ollama LLM calls in seconds (0 = no timeout) |
| `DPETML_INT8` | `0` | Use float32 for tracker feature arrays — halves memory vs float64 |
| `DPETML_TAB_RATE` | `30.0` | Min seconds between autonomous OPEN_APP actions |

### Quiet Mode (reduce fan noise while gaming)
```bash
# Linux / macOS
DPETML_QUIET=1 python ui/pet.py

# Windows PowerShell
$env:DPETML_QUIET="1"; python ui/pet.py
```

### Low-memory mode
```bash
DPETML_MEM_MAX=100 DPETML_INT8=1 python ui/pet.py
```


## 🛠️ **Tools Used**
- **PyQt5** for GUI
- **SQLite3** for data storage
- **Isolation Forest** for anomaly detection
- **Google Speech Recognition** for voice commands
- **Fabric Carpet mod** for Minecraft integration
- **Ollama** for local LLM (gemma2:2b / gemma3:4b)
- **psutil** for cross-platform process detection (Minecraft auto-detect on Windows + Linux)
- **[ToffeCraft Cat Asset Pack](https://toffeecraft.itch.io/cat-pack)** for animations

## ✨ **Desktop Pet Features:**
- 🎤 **STT commands** - Voice control your computer
- 📊 **Learns YOUR habits** - Adapts based on the apps you use
- 💬 **Smart commentary** - Talks about what you're currently doing occasionally
- 🎭 **Multiple animations** - Randomized behaviors keep it interesting
- 🥚 **Easter egg animations** - Hidden surprises for some interactions
- ⏰ **Time-based moods** - Different behaviors throughout the day
- ⚡ **Adaptive polling** - Slows down when idle, speeds up when Minecraft is running
- 🐧 **Linux support** - XDG paths, xdotool window detection, psutil MC detection

## 🎮 **Minecraft Bot Features:**
- 🤖 **Autonomous pet** - Spawns as a fake player in your world
- 💬 **Chat responses** - Reacts to what you say
- 🎁 **Item reactions** - Different responses for different items (fish, diamonds, plushies, etc)
- 🚶 **Movement** - Can walk, look around, jump
- 🧠 **Personality traits** - Curiosity, affection, aggression, boredom (affects behavior)
- 📚 **Memory system** - Remembers chat and events (WIP - see warning above)
- 🎨 **Custom skins** - Uses your chosen player's skin automatically
- 📏 **Scalable** - Adjust size to your preference
- 🎭 **Richer actions** - Explores, inspects blocks, paces, cheers, and more autonomous behaviours

## 🧠 **How it works**

### Desktop Pet
**Pet ML** uses platform-native APIs (pygetwindow on Windows, xdotool on Linux) to monitor your active applications. It sends app titles to a local LLM for categorization, then tracks:
- 🖥️ Which apps you use
- ⏱️ When you open them
- ⌛ How long you keep them open
- 📂 What category they belong to

Using **Isolation Forest**, it trains on this data from sqlite to detect outliers in your habits and routines.

The GUI threads both STT and ML processing while displaying animations and chat bubbles. User interactions trigger different animations, and time-based events (like lying down after idle periods) create natural pet behaviors.

The **Personality Engine** uses ML readings to randomly select preset dialog based on the pet's mood and reaction to your current activity.

### Minecraft Bot
The bot runs as a **Fabric Carpet fake player** on your Minecraft server. It:
- Receives commands via HTTP bridge (port 5050)
- Monitors context (position, held items, nearby blocks)
- Processes chat via LLM to generate responses
- Updates personality traits based on items you give it
- Stores memories in a tiered system (recent → important → archive)
- Auto-detects Minecraft via `psutil` process scan (Windows + Linux, even when MC is in the background)

### ⚠️ **Minecraft Gameplay Requirements**
- **CPU/GPU Intensive:** Minecraft gameplay is resource-intensive. Ensure your system has adequate CPU and GPU resources.
- **Required Mods:** You must install the **Carpet Mod** and **Carpet Addon** for Minecraft integration to work.
- **LLM Setup:** If you wish to play with LLM capabilities, you need to download the `.sc` (Scarpet) file from your Minecraft directory and move it into the scripts file of your minecraft world.
- **Plug & Play:** Without LLM setup, the desktop pet executable is plug and play — just run and enjoy!

**Data Flow:**
```
Minecraft (Scarpet) → Flask Bridge → Python Agents → Ollama LLM → Response → Bot Action
```

## 🔍 **Transparency**
**Human-written (85%):**
- 🧠 Core ML logic and behavioral pattern detection
- �� App tracking and categorization system
- 🎯 Overall architecture and design decisions
- 🗣️ STT command system and personality engine
- 🔄 Data migration and SQLite integration
- 🐛 Problem-solving and debugging
- 🎮 Minecraft integration and Scarpet scripting

**AI-assisted (15%):**
- 🎨 PyQt5 GUI implementation (unfamiliar with the library)
- 🔧 Some SQLite syntax and database operations
- 🐞 Debugging help for specific technical issues
- 🌐 Flask bridge boilerplate
- 🎨 Readme Lol

## 📝 **Known Issues**
- ⚠️ **Minecraft memory is unreliable** — stores events but LLM context injection is inconsistent
- ⚠️ **Sit feature doesn't work** — JustSit mod uses V-key which fake players can't simulate
- ⏱️ **Latency on Minecraft responses** — LLM takes 1-3 seconds per response (unavoidable with local models)
- **Slow initial load** — First response while loading model into memory

## 📄 **License**
### Code License (MIT)
The source code in this repository is free to use, modify, and distribute for any purpose, including commercial use.

**You are free to:**
- ✅ Use the code for personal projects
- ✅ Modify and adapt the code
- ✅ Distribute the modified code

**Requirements:**
- 📝 Credit the original author in your documentation/about section
- 🔗 Link back to this repository when possible

### Complete Application License
The **complete desktop pet application** (including animations, assets, and executable) is available for purchase:

**Personal Use:** Free (download from GitHub releases)
**Commercial Use:** Purchase required ($3 min)
- 🛒 [itch.io](https://bthegamedev.itch.io/desktoppet)

### Third-Party Assets
- **Cat Animations:** [ToffeCraft Cat Asset Pack](https://toffeecraft.itch.io/cat-pack) - Licensed separately
- **Ollama & Models:** [Ollama](https://ollama.ai) - License varies by model

## Tips
**If you like my work feel free to support me and other projects**
- 💵 [Cashapp](https://cash.app/$moneyplayb)
