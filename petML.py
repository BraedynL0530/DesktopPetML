import time
from datetime import datetime
import os
import json
import sqlite3
import threading
import joblib
import ollama
import pygetwindow as gw
from sklearn.ensemble import IsolationForest
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
import sqlite3
import threading


class PetAI:
    def __init__(self, db_path='pet_memory.db'):
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
        prompt = f"what type of app is {appName}, eg: coding(if it ends with .py its coding), gaming, browser, utility(OS STUFF ONLY), And social. One word, using only example words"
        response = ollama.chat(model='gemma3:4b', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content'].strip().lower()

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

    def load_from_file(self, filepath='pet_memoryOLD.json'):
        """Legacy JSON loader - only use for migration"""
        if not os.path.exists(filepath):
            print(f"No JSON file found at {filepath}")
            return

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            # Migrate JSON data to SQLite if database is empty
            if not self.chatHistory and not self.appMemory:
                self.appMemory = data.get('appMemory', {})
                self.chatHistory = data.get('chatHistory', [])
                print(f"Migrated data from JSON: {len(self.appMemory)} apps, {len(self.chatHistory)} sessions")
                self.save_to_db()  # Save migrated data
            else:
                print("SQLite data exists, skipping JSON migration")

        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"JSON file error: {e}")

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

            # Predict time habit
            time_input = [[stHour, category_id]]
            time_scaled = self.scaler.transform(time_input)
            time_outlier = self.timeHabitModel.fit_predict(time_scaled)[0]

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
                print("NORMAL: Everything as expected (smug mode)")

        except Exception as e:
            print(f"Model prediction error: {e}")

    def train_Model_On_History(self):
        if len(self.chatHistory) < 10:  # Need minimum data
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

        # Train models
        timeHabitModel = DBSCAN(eps=0.5, min_samples=2)  # Better params
        scaler = StandardScaler()
        scaled_timeHabitData = scaler.fit_transform(timeHabitData)

        durationModel = IsolationForest(contamination=0.1, random_state=42)  # 10% outliers

        durationModel.fit(durationData)
        timeHabitModel.fit(scaled_timeHabitData)

        # Store trained models
        self.durationModel = durationModel
        self.timeHabitModel = timeHabitModel
        self.scaler = scaler
        self.categoryMap = categoryMap

        self.save_models()
        print(f"Models trained successfully! Categories: {list(categoryMap.keys())}")

    def save_models(self, filepath_prefix='pet_model'):
        try:
            joblib.dump(self.durationModel, f'{filepath_prefix}_durationModel.joblib')
            joblib.dump(self.timeHabitModel, f'{filepath_prefix}_timeHabitModel.joblib')
            joblib.dump(self.scaler, f'{filepath_prefix}_scaler.joblib')
            joblib.dump(self.categoryMap, f'{filepath_prefix}_categoryMap.joblib')
            print("Models saved successfully!")
        except Exception as e:
            print(f"Model saving failed: {e}")

    def load_models(self, filepath_prefix='pet_model'):
        try:
            self.durationModel = joblib.load(f'{filepath_prefix}_durationModel.joblib')
            self.timeHabitModel = joblib.load(f'{filepath_prefix}_timeHabitModel.joblib')
            self.scaler = joblib.load(f'{filepath_prefix}_scaler.joblib')
            self.categoryMap = joblib.load(f'{filepath_prefix}_categoryMap.joblib')
            print("Models loaded successfully!")
            return True
        except Exception as e:
            print(f"No saved models found (this is normal on first run): {e}")
            return False

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

    # Try to load legacy JSON data for migration(wont apply for others just mine because i started from json
    pet.load_from_file()

    # Train models if we have enough data
    if len(pet.chatHistory) >= 10:
        pet.train_Model_On_History()

    try:
        while True:
            pet.app_Tracking()
            pet.model()

            time.sleep(5)

            # Retrain every 20 new records
            if len(pet.chatHistory) > 0 and len(pet.chatHistory) % 20 == 0:
                pet.train_Model_On_History()

    except KeyboardInterrupt:
        print("Shutting down, saving data...")
        pet.force_save()