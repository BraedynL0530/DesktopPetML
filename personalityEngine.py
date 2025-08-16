import random
import time
import json
from petML import PetAI



class Personality:
    def __init__(self, pet_instance, gui_instance, mood_lines):
        self.pet = pet_instance
        self.gui = gui_instance               # <-- Add this to call GUI methods
        self.currentMood = "smug"
        self.currentState = "normal"
        self.moodLines = mood_lines
        self.isTalking = False
        self.lastTalkTime = time.time()

    def getMood(self):
        if self.pet.surprised:
            self.currentMood = "surprised"
        elif self.pet.curious:
            self.currentMood = "curious"
        else:
            self.currentMood = "smug"

    def randomTalk(self):
        now = time.time()
        if now - self.lastTalkTime > 6:
            self.getMood()
            category = self.pet.categorize(self.pet.activeApp)
            line = random.choice(
                self.moodLines.get(self.currentMood, ["uh..."])
            ).format(appName=self.pet.activeApp, category=category)
            self.talk(line)
            self.lastTalkTime = now

    def talk(self, line):
        self.isTalking = True
        self.gui.showChat(line)#removed TTS as of now, the voice was horrid and buggy
        self.isTalking = False

    def bored(self):
        self.currentMood = "bored"
        self.randomTalk()




