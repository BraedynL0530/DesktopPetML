#STT AND COMMANDS
import os
import subprocess
from rapidfuzz import process
import pyautogui
from agents import agents


def command(text):
    text = text.lower()

    commandMap = { #t = text
        "screenshot": {"args": False, "fn": lambda _: pyautogui.screenshot()},
        "new tab": {"args": False, "fn": lambda _: pyautogui.hotkey("ctrl", "t")},
        "hey cat": {"args": True, "fn": lambda t: agents.handle({"type":"STT_COMMAND","text":t})},
    }
    match, score, _ = process.extractOne(text, commandMap.keys())

    if score < 80:
        print("No confident command match")
        return

    cmd = commandMap[match]

    if cmd["args"]:
        cmd["fn"](text)
    else:
        cmd["fn"](None)

def appOpen(text):
    app = text.split(" ", 1)[1].strip()

    try:
        subprocess.Popen([app.title()+'.exe'])
    except FileNotFoundError:
        print("app not found")








