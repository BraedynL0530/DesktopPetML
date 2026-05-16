import time
from datetime import datetime
from sklearn.ensemble import IsolationForest
import joblib
import os
import sys
import core.memory
from core.platform_utils import get_data_dir


def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()

# Use XDG / platform-appropriate data directory for model storage.
# This ensures models are stored in the right place on Linux (~/.local/share)
# and Windows (%APPDATA%) instead of being written next to the source code.
MODEL_DIR = os.path.join(get_data_dir(), "models")


def _numpy_dtype():
    """
    Return the numpy dtype to use for feature arrays.

    When ENABLE_INT8_QUANTIZATION is True the tracker uses float32 instead
    of the default float64, halving the memory footprint of feature arrays.
    scikit-learn IsolationForest does not support int8 natively, so float32
    is the practical minimum-precision option for this stack.
    """
    try:
        from core.config import ENABLE_INT8_QUANTIZATION
        if ENABLE_INT8_QUANTIZATION:
            import numpy as np
            return np.float32
    except Exception:
        pass
    return None  # let numpy/sklearn pick the default (float64)


class AppTracker:
    """
    Minimal tracker - just tracks timing and predicts anomalies
    NO database, NO LLM, NO categorization (those are delegated)
    """

    def __init__(self):
        # Current state
        self.activeApp = None
        self.startTime = None

        # ML models (loaded/trained later)
        self.durationModel = None
        self.timeHabitModel = None
        self.categoryMap = {}

        # Prediction results
        self.surprised = False  # Unusual duration
        self.curious = False  # Unusual timing

        # Load models if they exist
        self.load_models()

    def start_tracking(self, app_name: str):
        """
        Called when user switches apps
        Returns: session data if switching FROM another app, else None
        """
        now = datetime.now()

        session_data = None

        # If we were tracking something else, save that session
        if self.activeApp and self.startTime and self.activeApp != app_name:
            duration = (now - self.startTime).total_seconds()
            session_data = {
                'app': self.activeApp,
                'startTime': self.startTime.isoformat(),
                'endTime': now.isoformat(),
                'durationSeconds': duration
            }

        # Start tracking new app
        self.activeApp = app_name
        self.startTime = now

        return session_data

    def predict_anomalies(self, session: dict, category: str):
        """
        Given a session + category, predict if it's unusual
        Updates self.surprised and self.curious
        """
        if not self.durationModel or not self.timeHabitModel:
            print("⚠️ Models not trained yet")
            self.surprised = False
            self.curious = False
            return

        # Reset states
        self.surprised = False
        self.curious = False

        try:
            start = datetime.fromisoformat(session['startTime'])
            duration = session['durationSeconds'] / 60  # minutes
            start_hour = start.hour + start.minute / 60

            # Get category ID
            category_id = self.categoryMap.get(category, -1)
            if category_id == -1:
                print(f"Unknown category: {category}")
                return

            # Predict duration outlier
            dur_input = [[duration, category_id]]
            dur_outlier = self.durationModel.predict(dur_input)[0]

            # Predict time outlier
            time_input = [[start_hour, category_id]]
            time_outlier = self.timeHabitModel.predict(time_input)[0]

            # Set flags
            if dur_outlier == -1:
                self.surprised = True


            if time_outlier == -1:
                self.curious = True


        except Exception as e:
            print(f"Prediction error: {e}")

    def train_on_history(self, history: list):
        """
        Train models on session history.
        history = [{'startTime': '...', 'durationSeconds': 123, 'category': 'gaming'}, ...]

        When ENABLE_INT8_QUANTIZATION is set in config, feature arrays are
        stored as float32 instead of float64 to halve memory usage.
        """
        if len(history) < 10:
            print("⚠️ Need at least 10 sessions to train")
            return False

        print(f"Training on {len(history)} sessions...")

        # Build category map
        categories = list({s['category'] for s in history})
        self.categoryMap = {cat: idx for idx, cat in enumerate(categories)}

        # Extract features
        duration_data = []
        time_data = []

        for session in history:
            try:
                start = datetime.fromisoformat(session['startTime'])
                duration = session['durationSeconds'] / 60
                start_hour = start.hour + start.minute / 60
                category_id = self.categoryMap.get(session['category'], -1)

                if category_id != -1:
                    duration_data.append([duration, category_id])
                    time_data.append([start_hour, category_id])
            except Exception as e:
                print(f"Skipping bad session: {e}")
                continue

        if not duration_data or not time_data:
            print("No valid training data")
            return False

        # Optionally reduce precision to float32 to save memory
        dtype = _numpy_dtype()
        if dtype is not None:
            try:
                import numpy as np
                # Use np.asarray to avoid an unnecessary copy if already an array
                duration_data = np.asarray(duration_data, dtype=dtype)
                time_data = np.asarray(time_data, dtype=dtype)
            except Exception:
                pass  # fall back to default dtype if numpy conversion fails

        # Train models
        self.durationModel = IsolationForest(contamination=0.1, random_state=42)
        self.timeHabitModel = IsolationForest(contamination=0.1, random_state=42)

        self.durationModel.fit(duration_data)
        self.timeHabitModel.fit(time_data)

        self.save_models()
        print(f"✓ Models trained! Categories: {list(self.categoryMap.keys())}")
        return True

    def save_models(self, prefix='pet_model'):
        """Save trained models to disk"""
        if not os.path.exists(MODEL_DIR):
            os.makedirs(MODEL_DIR)

        try:
            joblib.dump(self.durationModel, os.path.join(MODEL_DIR, f'{prefix}_duration.joblib'))
            joblib.dump(self.timeHabitModel, os.path.join(MODEL_DIR, f'{prefix}_time.joblib'))
            joblib.dump(self.categoryMap, os.path.join(MODEL_DIR, f'{prefix}_categories.joblib'))
            print("✓ Models saved")
        except Exception as e:
            print(f"Model save failed: {e}")

    def load_models(self, prefix='pet_model'):
        """Load trained models from disk"""
        try:
            self.durationModel = joblib.load(os.path.join(MODEL_DIR, f'{prefix}_duration.joblib'))
            self.timeHabitModel = joblib.load(os.path.join(MODEL_DIR, f'{prefix}_time.joblib'))
            self.categoryMap = joblib.load(os.path.join(MODEL_DIR, f'{prefix}_categories.joblib'))
            print("✓ Models loaded")
            return True
        except Exception as e:
            print(f"No models found: {e}")
            return False