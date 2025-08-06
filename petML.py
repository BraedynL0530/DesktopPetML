import time
from datetime import datetime
import os
import json

import joblib
import ollama
import pygetwindow as gw
from sklearn.ensemble import IsolationForest
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler




class PetAI:
    def __init__(self):
        self.appMemory = {}
        self.chatHistory = []
        self.activeApp = None
        self.startTime = None
        self.surprised = False
        self.curious = False
        self.normal = True
        self.load_models()



    def getSecondTopWindow(self):
        fg = gw.getActiveWindow()
        if fg and fg.title:
            return fg.title

        #Below code is commented incase I need it later, oddly the pet gui isn't registering as the foreground anymore
        #may be removed if this persists!

        #windows = [w for w in gw.getAllWindows() if w.title and w.visible]
        #if not windows:
        #    return None

        #fg = gw.getActiveWindow()
        #if not fg:
        #    return None

        #try:
        #    idx = windows.index(fg)
        #except ValueError:
        #    return None

        #if idx + 1 < len(windows):
        #    return windows[idx + 1].title
        #return None


    def categorize(self, appName):
        if appName in self.appMemory:
            return self.appMemory[appName]

        category = self.getCatgory(appName)
        self.appMemory[appName] =category
        return category


    def getCatgory(self, appName):
        prompt = f"what type of app is {appName}, eg: coding, gaming, browser, and Social. One word, using only example words"
        response = ollama.chat(model='gemma3:4b', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content'].strip().lower()


    def appTracking(self):
        print("PetAI.appTracking called")
        appName = self.getSecondTopWindow()
        if not appName:
            return

        now = datetime.now()

        if self.activeApp != appName:
            if self.activeApp and self.startTime:
                # Save usage session for previous app
                endTime = now
                duration = (endTime - self.startTime).total_seconds()
                category = self.appMemory.get(self.activeApp, 'unknown')

                usage_record = {
                    'app': self.activeApp,
                    'category': category,
                    'startTime': self.startTime.isoformat(),
                    'endTime': endTime.isoformat(),
                    'durationSeconds': duration
                }
                self.chatHistory.append(usage_record)
                print(f"Stopped using {self.activeApp} at {endTime.strftime('%H:%M:%S')} after {duration:.2f} seconds.")

            self.activeApp = appName
            self.startTime = now

            category = self.categorize(appName)
            print(f"Switched to: {appName} ({category})")
            print("memory:",self.appMemory)
            print("chatH:",self.chatHistory)

    def saveToFile(self, filepath='pet_memory.json'):
        print("save called!")
        data = {
            'chatHistory': self.chatHistory,
            'appMemory': self.appMemory
        }
        with open(filepath, 'w') as f:
            json.dump(data, f ,indent=2)



    def load_from_file(self, filepath='pet_memory.json'):
        if not os.path.exists(filepath):
            print(f"No existing file found at {filepath}")
            return

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                self.appMemory = data.get('appMemory', {})
                self.chatHistory = data.get('chatHistory', [])
            print(f"Data loaded from {filepath}")
        except (json.JSONDecodeError, FileNotFoundError):
            # File is corrupted or empty, start fresh
            print(f"Corrupted file {filepath}, starting fresh")
            self.appMemory = {}
            self.chatHistory = []

    def model(self):
        if not hasattr(self, 'durationModel') or not hasattr(self, 'timeHabitModel'):
            print("⚠️ Model not trained yet.")
            return
        print("model in use")

        latest = self.chatHistory[-1]
        try:
            start = datetime.fromisoformat(latest['startTime'])
            duration = latest['durationSeconds'] / 60  # in minutes
            stHour = start.hour + start.minute / 60
            category_id = self.categoryMap.get(latest['category'], -1)

            if category_id == -1:
                return

            # Predict duration outlier
            dur_input = [[duration, category_id]]
            dur_outlier = self.durationModel.predict(dur_input)[0]

            # Predict time habit
            time_input = [[stHour, category_id]]
            time_scaled = self.scaler.transform(time_input)
            time_outlier = self.timeHabitModel.fit_predict(time_scaled)[0]
            # Decide actions
            if dur_outlier == -1:
                self.surprised = True #assuming its longer that normal
            else:
                normal = True
            if time_outlier == -1:
                self.curious = True
            else:
                normal = True


            #make list of dialog options for each here or in separate function.
        except Exception as e:
            print("error in model!")


    def trainModelOnHistory(self):
        chatHistory = self.chatHistory
        appMem = self.appMemory

        categories = list({i['category'] for i in self.chatHistory})
        categoryMap = {cat: idx for idx, cat in enumerate(categories)}

        timeHabitData = []
        durationData = []


        for i in self.chatHistory:
            try:
                startTime = datetime.fromisoformat(i['startTime'])
                duration = i['durationSeconds'] / 60  # minutes

                sHour = startTime.hour + startTime.minute / 60

                category_id = categoryMap.get(i['category'], -1)
                durationData.append([duration,category_id])
                timeHabitData.append([sHour, category_id])
            except:
                continue

        if not timeHabitData or not durationData:
            print("no data yet")
            return

        timeHabitModel = DBSCAN()
        scaler = StandardScaler()
        scaled_timeHabitData = scaler.fit_transform(timeHabitData)

        durationModel = IsolationForest(contamination=0.05, random_state=42)


        durationModel.fit(durationData)
        timeHabitModel.fit(scaled_timeHabitData)

        timeHabitPredictions = durationModel.predict(timeHabitData)
        durPredictions = durationModel.predict(durationData)

        self.durationModel = durationModel
        self.timeHabitModel = timeHabitModel
        self.scaler = scaler
        self.categoryMap = categoryMap

    def save_models(self, filepath_prefix='pet_model'):
        # Save all model-related objects
        joblib.dump(self.durationModel, f'{filepath_prefix}_durationModel.joblib')
        joblib.dump(self.timeHabitModel, f'{filepath_prefix}_timeHabitModel.joblib')
        joblib.dump(self.scaler, f'{filepath_prefix}_scaler.joblib')
        joblib.dump(self.categoryMap, f'{filepath_prefix}_categoryMap.joblib')
        print("Models saved!")

    def load_models(self, filepath_prefix='pet_model'):
        try:
            self.durationModel = joblib.load(f'{filepath_prefix}_durationModel.joblib')
            self.timeHabitModel = joblib.load(f'{filepath_prefix}_timeHabitModel.joblib')
            self.scaler = joblib.load(f'{filepath_prefix}_scaler.joblib')
            self.categoryMap = joblib.load(f'{filepath_prefix}_categoryMap.joblib')
            print("Models loaded!")
        except Exception as e:
            print("Model loading failed or no saved model found:", e)

    def updateStatus(self):
        # Here refresh activeApp, surprised, curious, or any other states
        # For example:
        self.activeApp = self.getSecondTopWindow()
        self.surprised = self.surprised
        self.curious = self.curious

if __name__ == "__main__":
    pet = PetAI()
    pet.load_from_file()  # Load memory when you start

    try:
        while True:
            pet.appTracking()
            pet.model()

            time.sleep(5)
            if len(pet.chatHistory) % 10 == 0:
                pet.trainModelOnHistory()
    except KeyboardInterrupt:
        print("Shutting down, saving data...")
        pet.saveToFile()  # Save memory when shutting down