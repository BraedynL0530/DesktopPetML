#STT AND COMMANDS
import vosk
import sys
import pyaudio
import json
from pet import pet_gui

model = vosk.Model('vosk-model-small-en-us-0.15')
rec = vosk.KaldiRecognizer(model, 16000)

p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8000)

pet = pet_gui
def command(text):

    # not the most efficent STT command but itl do
    text = text.lower
    commandMap = {
        "placeH": lambda: print("placeholder"),
        "placeH": lambda: print("placeholder"),
        "placeH": lambda: print("placeholder"),
        # add more commands
    }

    for key in commandMap:
        if key in text:
            commandMap[key]()
            return



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



