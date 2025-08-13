#STT AND COMMANDS
import vosk
import os
import subprocess
import pyaudio
import json
from pet import pet_gui
import pyautogui
from rapidfuzz import process
model = vosk.Model('vosk-model-small-en-us-0.15')
rec = vosk.KaldiRecognizer(model, 16000)
pet = pet_gui
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8000)



def command(text):
    # not the most efficient STT command but itl do
    text = text.lower()

    commandMap = {
        "screen shot": lambda: pyautogui.screenshot(),
        "open": lambda t: appOpen(t),
        "placeH3": lambda: print("placeholder"),
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

while True:
    if pet.clicked and pet.click_times ==1:
        if not stream_active:
            stream.start_stream()
            stream_active = True
        data = stream.read(4000, exception_on_overflow=False)
        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            text = result['text']
            command(text)
            print("Final text:", text)
        else:
            print(json.loads(rec.PartialResult())['partial'])
    elif len(pet.click_times) > 1:
        if stream_active:
            stream.stop_stream()
            stream_active = False



