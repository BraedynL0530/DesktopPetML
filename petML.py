import time
from datetime import datetime
import os
import json
import joblib
import ollama
import pygetwindow as gw
from sklearn.ensemble import IsolationForest
import sqlite3
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "pet_memory.db")
MODEL_DIR = os.path.join(BASE_DIR, "models")


class PetAI:
    def __init__(self, db_path=DB_DIR,):
        self.db_path = db_path
        self.appMemory = {}
        self.chatHistory = []
        self.activeApp = None
        self.startTime = None
        self.surprised = False
        self.curious = False
        self.normal = True
        self.lock = threading.Lock()
        self.last_saved_count = 0  # Initialize properly

        self._init_db()
        self.load_from_db()
        self.load_models()  # Load models on startup
        self.last_retrain = 0

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                      CREATE TABLE IF NOT EXISTS appMemory
                      (
                          appName
                          TEXT
                          PRIMARY
                          KEY,
                          category
                          TEXT
                      )
                      ''')
            c.execute('''
                      CREATE TABLE IF NOT EXISTS chatHistory
                      (
                          id
                          INTEGER
                          PRIMARY
                          KEY
                          AUTOINCREMENT,
                          app
                          TEXT,
                          category
                          TEXT,
                          startTime
                          TEXT,
                          endTime
                          TEXT,
                          durationSeconds
                          REAL
                      )
                      ''')
            conn.commit()

    def load_from_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT appName, category FROM appMemory")
            rows = c.fetchall()
            self.appMemory = {app: cat for app, cat in rows}

            c.execute("SELECT app, category, startTime, endTime, durationSeconds FROM chatHistory ORDER BY id")
            self.chatHistory = [
                {'app': app, 'category': cat, 'startTime': st, 'endTime': et, 'durationSeconds': dur}
                for app, cat, st, et, dur in c.fetchall()
            ]

        self.last_saved_count = len(self.chatHistory)  # Set after loading
        print(f"Loaded {len(self.appMemory)} appMemory entries and {len(self.chatHistory)} chatHistory entries")

    def save_to_db(self):
        self.clean_bad_categories()
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                # Replace entire appMemory table
                c.execute("DELETE FROM appMemory")
                for app, cat in self.appMemory.items():
                    c.execute("INSERT INTO appMemory (appName, category) VALUES (?, ?)", (app, cat))

                # To avoid duplicates, clear chatHistory and reinsert
                c.execute("DELETE FROM chatHistory")
                for record in self.chatHistory:
                    c.execute('''INSERT INTO chatHistory (app, category, startTime, endTime, durationSeconds)
                                 VALUES (?, ?, ?, ?, ?)''',
                              (record['app'], record['category'], record['startTime'], record['endTime'],
                               record['durationSeconds']))

                conn.commit()

        self.last_saved_count = len(self.chatHistory)  # Update after saving
        print(f"Saved {len(self.chatHistory)} records to SQLite database")

    def getSecondTopWindow(self):
        fg = gw.getActiveWindow()
        if fg and fg.title:
            return fg.title

        # Below code is commented incase I need it later, oddly the pet gui isn't registering as the foreground anymore
        # may be removed if this persists!

        # windows = [w for w in gw.getAllWindows() if w.title and w.visible]
        # if not windows:
        #    return None

        # fg = gw.getActiveWindow()
        # if not fg:
        #    return None

        # try:
        #    idx = windows.index(fg)
        # except ValueError:
        #    return None

        # if idx + 1 < len(windows):
        #    return windows[idx + 1].title
        # return None

    def categorize(self, appName):
        if appName in self.appMemory:
            return self.appMemory[appName]

        category = self.get_Catgory(appName)
        self.appMemory[appName] = category
        return category

    def get_Catgory(self, appName):
        prompt = f"what type of app is {appName}, eg: coding(if it ends with .py its coding), gaming, browser, utility(OS STUFF ONLY), And social. One word, using only example words"#shouldve know i needed a failsafe smh
        response = ollama.chat(model='gemma3:4b', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content'].strip().lower()

    def clean_bad_categories(self):
        valid_cats = ['coding', 'gaming', 'browser', 'utility', 'social']

        # Clean appMemory
        for app, cat in list(self.appMemory.items()):
            if cat not in valid_cats:
                # Re-categorize the app
                self.appMemory[app] = self.get_Catgory(app)

        # Clean chatHistory
        for record in self.chatHistory:
            if record['category'] not in valid_cats:
                app_name = record['app']
                record['category'] = self.appMemory.get(app_name, 'utility')



    def app_Tracking(self):
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
                print(
                    f"Stopped using {self.activeApp} at {endTime.strftime('%H:%M:%S')} after {duration:.2f} seconds.")

            self.activeApp = appName
            self.startTime = now

            category = self.categorize(appName)


            current_count = len(self.chatHistory)
            if current_count > self.last_saved_count and (current_count - self.last_saved_count) >= 3:
                print(f"Auto-saving: {current_count - self.last_saved_count} new records")
                self.save_to_db()

            print(f"Switched to: {appName} ({category})")
            print(f"Memory: {len(self.appMemory)} apps, History: {len(self.chatHistory)} sessions")


    def model(self):
        if not hasattr(self, 'durationModel') or not hasattr(self, 'timeHabitModel'):
            print("⚠️ Models not loaded/trained yet")
            return

        if not self.chatHistory:
            print("⚠No chat history for model prediction")
            return

        print("Running model predictions...")

        # Reset states first
        self.surprised = False
        self.curious = False
        self.normal = True

        latest = self.chatHistory[-1]
        try:
            start = datetime.fromisoformat(latest['startTime'])
            duration = latest['durationSeconds'] / 60  # in minutes
            stHour = start.hour + start.minute / 60
            category_id = self.categoryMap.get(latest['category'], -1)

            if category_id == -1:
                print(f"Unknown category: {latest['category']}")
                return

            # Predict duration outlier
            dur_input = [[duration, category_id]]
            dur_outlier = self.durationModel.predict(dur_input)[0]

            # FIXED: Predict time habit using same approach
            time_input = [[stHour, category_id]]  # No scaling needed for IsolationForest
            time_outlier = self.timeHabitModel.predict(time_input)[0]

            print(f"Duration outlier: {dur_outlier}, Time outlier: {time_outlier}")

            # Set states based on predictions
            if dur_outlier == -1:
                self.surprised = True
                self.normal = False
                print("SURPRISED: Unusual duration detected!")

            if time_outlier == -1:
                self.curious = True
                self.normal = False
                print("CURIOUS: Unusual time pattern detected!")

            if self.normal:
                print("NORMAL: Everything as expected")

        except Exception as e:
            print(f"Model prediction error: {e}")

    def train_Model_On_History(self):
        if len(self.chatHistory) < 10:
            print("⚠Not enough data to train models yet")
            return

        print("Training models on history...")

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

                if category_id != -1:
                    durationData.append([duration, category_id])
                    timeHabitData.append([sHour, category_id])
            except Exception as e:
                print(f"Skipping bad record: {e}")
                continue

        if not timeHabitData or not durationData:
            print("No valid data for training")
            return

        # FIXED: Use IsolationForest for both
        durationModel = IsolationForest(contamination=0.1, random_state=42)
        timeHabitModel = IsolationForest(contamination=0.1, random_state=42)  # Same approach

        durationModel.fit(durationData)
        timeHabitModel.fit(timeHabitData)  # No scaling needed

        # Store trained models
        self.durationModel = durationModel
        self.timeHabitModel = timeHabitModel
        self.categoryMap = categoryMap

        self.save_models()
        print(f"Models trained successfully! Categories: {list(categoryMap.keys())}")

    def save_models(self, filepath_prefix='pet_model'):
        if not os.path.exists(MODEL_DIR):
            os.makedirs(MODEL_DIR)
        try:
            joblib.dump(self.durationModel, os.path.join(MODEL_DIR, f'{filepath_prefix}_durationModel.joblib'))
            joblib.dump(self.timeHabitModel, os.path.join(MODEL_DIR, f'{filepath_prefix}_timeHabitModel.joblib'))
            joblib.dump(self.categoryMap, os.path.join(MODEL_DIR, f'{filepath_prefix}_categoryMap.joblib'))
            print("Models saved successfully!")
        except Exception as e:
            print(f"Model saving failed: {e}")

    def load_models(self, filepath_prefix='pet_model'):
        try:
            self.durationModel = joblib.load(os.path.join(MODEL_DIR, f'{filepath_prefix}_durationModel.joblib'))
            self.timeHabitModel = joblib.load(os.path.join(MODEL_DIR, f'{filepath_prefix}_timeHabitModel.joblib'))
            self.categoryMap = joblib.load(os.path.join(MODEL_DIR, f'{filepath_prefix}_categoryMap.joblib'))
            print("Models loaded successfully!")
            return True
        except Exception as e:
            print(f"No saved models found: {e}")
            return False
        except Exception as e:
            print(f"Model saving failed: {e}")


    def force_save(self):
        """Manual save function"""
        print("Force saving all data...")
        self.save_to_db()
        if hasattr(self, 'durationModel'):
            self.save_models()

    def updateStatus(self):
        self.activeApp = self.getSecondTopWindow()



if __name__ == "__main__":
    pet = PetAI()


    # Train models if we have enough data
    if len(pet.chatHistory) >= 10:
        pet.train_Model_On_History()

    try:
        while True:
            pet.app_Tracking()
            pet.model()

            time.sleep(5)

            # Retrain
            if len(pet.chatHistory) > 0 and len(pet.chatHistory) % 50 == 0 and len(pet.chatHistory) != pet.last_retrain:
                pet.last_retrain = len(pet.chatHistory)
                pet.train_Model_On_History()

    except KeyboardInterrupt:
        print("Shutting down, saving data...")
        pet.force_save()