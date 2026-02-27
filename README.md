#  **DESKTOP PET w/ MINECRAFT & MACHINE LEARNING** 🤖🎮
A smart desktop companion that learns your computer habits, integrates with Minecraft, and reacts to your behavior!

## ⚠️ **STATUS**
- ✅ **Desktop pet is STABLE** - Full functionality with personality system
- ✅ **Minecraft integration WORKING** - Bot spawning, movement, chat, item reactions
- 🚧 **Minecraft memory system WIP** - Items detected, traits change, but memory retrieval is error-prone
  - Memory stores correctly but LLM context injection is inconsistent
  - Use at your own risk — may not remember things reliably
  - See `core/tiered_memory.py` for known issues
- ✅ **Need Ollama running** - Local LLM required (gemma3:4b or compatible)

## 📦 **Installation**
1. Install Ollama: https://ollama.ai
2. Pull model: `ollama pull gemma2:2b` (or gemma3:4b)
3. Clone repo and install deps: `pip install -r requirements.txt`
4. For Minecraft: Install Fabric + Carpet mod on your server

## 🎯 **Quick Start**
```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Start skin server (if using Minecraft)
cd your_project
python serve_skins.py

# Terminal 3: Run the pet
python pet.py
```

## 🎨 **PyInstaller Release Build**
To create a standalone executable for distribution:

```bash
pyinstaller --onefile --windowed --icon=path/to/icon.ico --add-data "skins:skins" --add-data "llm/prompts:llm/prompts" pet.py
```

**Output:** `dist/pet.exe`

**Flags explained:**
- `--onefile` - Single executable file
- `--windowed` - No console window
- `--icon` - Custom app icon
- `--add-data` - Include folders (skins, prompts) in executable
- `--add-binary` - Include DLLs if needed

**For Minecraft bot version:**
```bash
pyinstaller --onefile --windowed --icon=icon.ico --add-data "skins:skins" --add-data "llm/prompts:llm/prompts" --hidden-import=llm.ollama_client minecraft_agent_launcher.py
```

## 🛠️ **Tools Used**
- **PyQt5** for GUI
- **SQLite3** for data storage 
- **Isolation Forest** for anomaly detection
- **Google Speech Recognition** for voice commands
- **Fabric Carpet mod** for Minecraft integration
- **Ollama** for local LLM (gemma2:2b / gemma3:4b)
- **[ToffeCraft Cat Asset Pack](https://toffeecraft.itch.io/cat-pack)** for animations

## ✨ **Desktop Pet Features:**
- 🎤 **STT commands** - Voice control your computer
- 📊 **Learns YOUR habits** - Adapts based on the apps you use
- 💬 **Smart commentary** - Talks about what you're currently doing occasionally
- 🎭 **Multiple animations** - Randomized behaviors keep it interesting
- 🥚 **Easter egg animations** - Hidden surprises for some interactions
- ⏰ **Time-based moods** - Different behaviors throughout the day

## 🎮 **Minecraft Bot Features:**
- 🤖 **Autonomous pet** - Spawns as a fake player in your world
- 💬 **Chat responses** - Reacts to what you say
- 🎁 **Item reactions** - Different responses for different items (fish, diamonds, plushies, etc)
- 🚶 **Movement** - Can walk, look around, jump
- 🧠 **Personality traits** - Curiosity, affection, aggression, boredom (affects behavior)
- 📚 **Memory system** - Remembers chat and events (WIP - see warning above)
- 🎨 **Custom skins** - Uses your chosen player's skin automatically
- 📏 **Scalable** - Adjust size to your preference

## 🧠 **How it works**

### Desktop Pet
**Pet ML** uses `pygetwindow` to monitor your active applications. It sends app titles to a local LLM for categorization, then tracks:
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

**Data Flow:**
```
Minecraft (Scarpet) → Flask Bridge → Python Agents → Ollama LLM → Response → Bot Action
```

## 🔍 **Transparency** 
*(being honest about development)*

This project represents my learning journey in Python but I do need help with unfamiliar tech, so I use LLM as tools.

**Human-written (85%):**
- 🧠 Core ML logic and behavioral pattern detection
- 📊 App tracking and categorization system  
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

## 📝 **Known Issues**
- ⚠️ **Minecraft memory is unreliable** — stores events but LLM context injection is inconsistent
- ⚠️ **Sit feature doesn't work** — JustSit mod uses V-key which fake players can't simulate
- ⏱️ **Latency on Minecraft responses** — LLM takes 1-3 seconds per response (unavoidable with local models)
- 🐢 **Slow initial load** — First response while loading model into memory

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
**If you like my work feel free to tip** 💜
- 💵 [Cashapp](https://cash.app/$moneyplayb)
