#STT AND COMMANDS
import vosk
import os
import subprocess
from rapidfuzz import process
import pyautogui

model = vosk.Model('vosk-model-small-en-us-0.15')
rec = vosk.KaldiRecognizer(model, 16000)




def command(text):
    text = text.lower()

    commandMap = {
        "screen shot": lambda: pyautogui.screenshot(),
        "open": lambda t: appOpen(t),
        "new tab": lambda: pyautogui.hotkey("ctrl","t"),
        "close tab": lambda: pyautogui.hotkey("ctrl", "w"),
        "close all tabs": lambda: pyautogui.hotkey("ctrl","shift", "w"),
        "restore tabs": lambda: pyautogui.hotkey("ctrl", "shift", "t"),
        # add more commands
    }
    match, score, _ = process.extractOne(text, commandMap.keys())

    if score > 80:
        commandMap[match](text)
    else:
        print("Command not recognized.")

def appOpen(text):
    app = text.split(" ", 1)[1].strip()
    try:
        subprocess.Popen([app+'.exe'])
    except FileNotFoundError:
        print("app not found")



stream_active = False




