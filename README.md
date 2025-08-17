#  **DESKTOP PET w/ MACHINE LEARNING** 🤖

A smart desktop companion that learns your computer habits and reacts to your behavior!
## Tips
**If you like my work feel free to tip any of the two below:**
- ☕ [Ko-fi](https://bthegamedev.itch.io/desktoppet) =not license related!! (card isnt linked yet but feel free to donate)
-  $ CashApp $moneyplayb
  
## 🛠️ **Tools Used**
- **PyQt5** for GUI
- **SQLite3** for data storage 
- **Isolation Forest** for anomaly detection
- **Google Speech Recognition** for voice commands
- **[ToffeCraft Cat Asset Pack](https://toffeecraft.itch.io/cat-pack)** for animations

## ✨ **Features:**
- 🎤 **STT commands** - Voice control your computer
- 📊 **Learns YOUR habits** - Adapts based on the apps you use
- 💬 **Smart commentary** - Talks about what you're currently doing occasionally
- 🎭 **Multiple animations** - Randomized behaviors keep it interesting
- 🥚 **Easter egg animations** - Hidden surprises for some interactions
- ⏰ **Time-based moods** - Different behaviors throughout the day

## 🧠 **How it works**
**Pet ML** uses `pygetwindow` to monitor your active applications. It sends app titles to a local LLM for categorization, then tracks:
- 🖥️ Which apps you use
- ⏱️ When you open them  
- ⌛ How long you keep them open
- 📂 What category they belong to

Using **Isolation Forest**, it trains on this data from sqlite to detect outliers in your habits and routines.

The GUI threads both STT and ML processing while displaying animations and chat bubbles. User interactions trigger different animations, and time-based events (like lying down after idle periods) create natural pet behaviors.

The **Personality Engine** uses ML readings to randomly select preset dialog based on the pet's mood and reaction to your current activity.

**STT** (threaded from GUI) processes voice commands to trigger actions like:
- 📱 Opening applications
- 🔄 Restoring browser tabs  
- 🚀 More features coming soon!

## 🔍 **Transparency** 
*(being honest about development)*

This project represents my learning journey in Python but i do need help so i use LLM as tools in tech im unfamilar with.

**Human-written (85%):**
- 🧠 Core ML logic and behavioral pattern detection
- 📊 App tracking and categorization system  
- 🎯 Overall architecture and design decisions
- 🗣️ STT command system and personality engine
- 🔄 Data migration and SQLite integration
- 🐛 Problem-solving and debugging (like fixing the scaler issue)

**AI-assisted (15%):**
- 🎨 PyQt5 GUI implementation (unfamiliar with the library)
- 🔧 Some SQLite syntax and database operations
- 🐞 Debugging help for specific technical issues.

## 📄 **License**

### Code License (MIT-style)
The source code in this repository is free to use, modify, and distribute for any purpose, including commercial use.

**You are free to:**
- ✅ Use the code for personal or commercial projects
- ✅ Modify and adapt the code
- ✅ Distribute the modified code
- ✅ Sell software that incorporates this code

**Requirements:**
- 📝 Credit the original author in your documentation/about section
- 🔗 Link back to this repository when possible

### Complete Application License
The **complete desktop pet application** (including animations, assets, and executable) is available for purchase:

**Personal Use:** Free (download from GitHub releases)
**Commercial Use:** Purchase required $3 min
- 🛒 [itch.io](https://bthegamedev.itch.io/desktoppet)

### Third-Party Assets
- **Cat Animations:** [ToffeCraft Cat Asset Pack](https://toffeecraft.itch.io/cat-pack) - Licensed separately

---
**TL;DR:** Code is free for everyone, complete app with animations costs money for commercial use. Just give me credit! 
