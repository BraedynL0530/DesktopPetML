import random
import time
import json
import pyautogui
from petML import PetAI


class personality():
    def __init__(self,pet_instance):
        self.pet = pet_instance
        self.currentMood = "smug"
        self.currentState = "normal"
        self.moodLines = moodLines
        self.isTalking = False
        self.lastTalkTime = time.time()


    def getMood(self):
        if self.pet.surprised:
            self.currentMood = "surprised"
        if self.pet.curious:
            self.currentMood = "curious"
        else:
            self.currentMood = "smug"

    def randomTalk(self):
        now = time.time()
        if now - self.lastTalkTime > 30 :
            self.getMood()
            category = self.pet.categorize(self.pet.activeApp)
            line = random.choice(
                self.moodLines.get(self.currentMood, ["uh..."])
            ).format(appName=self.pet.activeApp, category=category)
            self.talk(line)
            self.lastTalkTime = now

    def talk(self,line):
        self.isTalking = True
        # right here needs to make a varible to return so that pyQt5 can display it in a chat bubble the varible is reset after it sends
        #tts placeholder
        time.sleep(1)
        self.isTalking = False


    def bored(self): #placeholder
        #idk how wanna do it maybe by how many times you click the cat in pyQt5 in an hour
        self.currentMood = "bored"
        self.randomTalk()




if __name__ == "__main__":
    with open("dialog.json", "r") as f:
        moodLines = json.load(f)
    personality()