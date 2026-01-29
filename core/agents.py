import pyautogui
import memory
import pygetwindow as gw
import personalityEngine
import tempfile
import os
from llm.ollama_client import LLMClient
from llm.response_parser import parse_intent



class agents:

    def __init__(self):
        self.mood = personalityEngine.EmotionalState
        self.intent = None
        self.taskDone = True
        #self.memory = memory.Memory()


    def get_active_app(self) -> [str]:#Optional
        fg = gw.getActiveWindow()
        if fg and fg.title:
            return fg.title
        return None

    def take_screenshot(self):
        path = None
        try:
            img = pyautogui.screenshot()

            with tempfile.NamedTemporaryFile(
                    suffix=".png",
                    delete=False
            ) as tmp:
                path = tmp.name
                img.save(path)

            self.handle({
                "type": "VISION_SNAPSHOT",
                "path": path,
                "source": "desktop"
            })

        finally:
            if path and os.path.exists(path):
                #saftey n shi
                os.remove(path)

    def searchWeb(self,query):
        return None

    def openApp(self,app):
        return None


    def vision(self, path):#describes img
        llm = LLMClient(model_name="llava")
        resp_text = llm.chat([
            {"role": "user", "content": "Describe this screenshot"}
        ])
        summary = resp_text
        return summary

    def handle(self,event):
        if event["type"] == "VISION_SNAPSHOT":
            path = event["path"]
            # call your vision model
            summary = self.vision(path)
            # maybe store in short-term memory
            self.memory.add("vision", summary)
            # optionally feed summary to LLM for decision
            intent = self.llm.decide(summary)
            self.execute(intent)
        if event["type"] == "STT_COMMAND":
            llm = LLMClient(model_name="gemma3:4b")  # idk that will work
            resp_text = llm.chat([
                {"role": "system", "content": open("llm/prompts/personality.txt").read()},
                {"role": "system", "content": open("llm/prompts/reasoning.txt").read()},
                {"role": "user", "content": event["text"]}
            ])
            intent = parse_intent(resp_text)
            if intent["intent"] == "DONE":
                self.taskDone = True

            else:
                self.execute(intent)
                self.taskDone = False



    def execute(self,intent):
        if intent["intent"] == "TAKE_SCREENSHOT":
            self.take_screenshot()

        if intent["intent"] == "OPEN_APP":
           self.openApp(intent["args"]["app"])

        if intent["intent"] == "SEARCH_WEB":
            self.searchWeb(intent["args"]["query"])