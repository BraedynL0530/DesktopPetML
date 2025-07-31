import time
from datetime import datetime
import ollama
import pygetwindow as gw


class PetAI:
    def __init__(self):
        self.appMemory = {}
        self.chatHistory = []
        self.activeApp = None
        self.startTime = None



    def getSecondTopWindow(self):
        windows = [w for w in gw.getAllWindows() if w.title and w.visible]
        if not windows:
            return None

        fg = gw.getActiveWindow()
        if not fg:
            return None

        try:
            idx = windows.index(fg)
        except ValueError:
            return None

        if idx + 1 < len(windows):
            return windows[idx + 1].title
        return None


    def categorize(self, appName):
        if appName in self.appMemory:
            return self.appMemory[appName]

        catogory = self.getCatgory(appName)
        self.appMemory[appName] = catogory
        return catogory


    def getCatgory(self, appName):
        prompt = f"what type of app is {appName}, eg: coding, gaming, browser, and other. One word, using only example words"
        response = ollama.chat(model='gemma3:4b', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content'].strip().lower()


    def appTracking(self):
        appName = self.getSecondTopWindow()
        if not appName:
            return

        now = datetime.now()

        if self.activeApp != appName:
            if self.activeApp and self.startTime:
                # Save usage session for previous app
                endTime = now
                duration = (endTime - self.startTime).total_seconds()
                usage_record = {
                    'app': self.activeApp,
                    'start_time': self.startTime,
                    'end_time': endTime,
                    'duration_seconds': duration
                }
                self.chatHistory.append(usage_record)
                print(f"Stopped using {self.activeApp} at {endTime.strftime('%H:%M:%S')} after {duration:.2f} seconds.")

            self.activeApp = appName
            self.startTime = now

            category = self.categorize(appName)
            print(f"Switched to: {appName} ({category})")

    def model(self):
        pass
if __name__ == "__main__":
    pet = PetAI()
    while True:
        pet.appTracking()
        time.sleep(5)  # adjust how often you want to check