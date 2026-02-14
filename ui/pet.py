"""
Desktop Pet GUI - PyQt5 Version with Proper Threading (FIXED v2)
Clean separation: GUI thread does UI, worker thread does AI/ML

INTEGRATION WITH EXISTING SYSTEMS:
- Uses core.messaging.RandomMessenger for personality
- Uses core.agent_bridge.AgentBridge for LLM commands
- No dialog.json dependency
- Proper integration with existing architecture
"""
import sys
import random
import time
import os, sys
import traceback

from PyQt5.QtCore import Qt, QTimer, QRect, QObject, pyqtSignal, QThread, QPoint
from PyQt5.QtGui import QPainter, QPixmap, QPolygon, QBrush, QColor
from PyQt5.QtWidgets import QApplication, QWidget, QLabel

import speech_recognition as sr

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.memory import Memory
from core.agent_bridge import AgentBridge
from core.tracking import AppTracker
from core.messaging import RandomMessenger
# ============================================================================
# PLATFORM DETECTION
# ============================================================================

class PlatformHelper:
    """Cross-platform window detection"""
    @staticmethod
    def get_active_app():
        try:
            import pygetwindow as gw
            fg = gw.getActiveWindow()
            if fg and fg.title:
                return fg.title
        except Exception as e:
            print(f"Platform detection error: {e}")
        return None


# ============================================================================
# WORKER THREAD - Handles all AI/ML work
# ============================================================================

class PetWorker(QObject):
    """
    Integrates with existing core modules:
    - core.memory for database
    - core.tracking for ML
    - core.agent_bridge for LLM integration
    """
    data_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False

        # Components
        self.memory = Memory()
        self.tracker = AppTracker()
        self.agent_bridge = AgentBridge()
        self.platform = PlatformHelper()

        # Cache for categories
        self.category_cache = {}

    def start_worker(self):
        """Initialize components (runs in worker thread)"""
        try:
            # Add parent directory to path for imports
            parent_dir = os.path.dirname(BASE_DIR)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)



            self.memory = Memory()
            self.tracker = AppTracker()

            # Load cached categories
            self.category_cache = self.memory.get_all_categories()

            # Load history and train models if enough data
            history = self.memory.get_all_sessions()
            if len(history) >= 10:
                print(f"Training on {len(history)} historical sessions...")
                self.tracker.train_on_history(history)
            else:
                print(f"Only {len(history)} sessions available. Need at least 10 to train.")

            self.running = True
            print("✓ Worker initialized")
        except Exception as e:
            error_msg = f"Worker initialization failed: {e}\n{traceback.format_exc()}"
            print(error_msg)
            self.error_occurred.emit(error_msg)

    def run(self):
        """Main loop"""
        self.start_worker()

        if not self.running:
            print("Worker failed to initialize, exiting...")
            return

        last_retrain = 0
        error_count = 0
        max_errors = 10

        while self.running:
            try:
                # Get active app from platform
                app_name = self.platform.get_active_app()
                if not app_name:
                    time.sleep(5)
                    continue

                # Track session
                session = self.tracker.start_tracking(app_name)

                # If we finished a session, save it
                if session:
                    category = self.get_category(session['app'])
                    session['category'] = category

                    # Save to database
                    self.memory.save_session(session)

                    # Run ML prediction
                    self.tracker.predict_anomalies(session, category)

                    print(f"Session: {session['app']} ({category}) - {session['durationSeconds']:.1f}s")

                # Send update to GUI
                current_category = self.get_category(app_name)
                self.data_updated.emit({
                    'surprised': self.tracker.surprised,
                    'curious': self.tracker.curious,
                    'activeApp': app_name,
                    'category': current_category
                })

                # Retrain periodically
                if self.memory:
                    session_count = self.memory.get_session_count()
                    if session_count > 0 and session_count % 50 == 0 and session_count != last_retrain:
                        print(f"Retraining models at {session_count} sessions...")
                        history = self.memory.get_all_sessions()
                        if self.tracker.train_on_history(history):
                            last_retrain = session_count

                # Reset error counter on success
                error_count = 0
                time.sleep(5)

            except Exception as e:
                error_count += 1
                error_msg = f"Worker error ({error_count}/{max_errors}): {e}"
                print(error_msg)

                if error_count >= max_errors:
                    print("Too many errors, stopping worker...")
                    self.error_occurred.emit("Worker encountered too many errors and stopped")
                    break

                time.sleep(1)

    def get_category(self, app_name: str) -> str:
        """Get category for an app"""
        if not app_name:
            return 'unknown'

        # Check cache first
        if app_name in self.category_cache:
            return self.category_cache[app_name]

        # Check database
        if self.memory:
            category = self.memory.get_category(app_name)
            if category != 'unknown':
                self.category_cache[app_name] = category
                return category

        # Fallback categorization
        category = self._simple_categorize(app_name)

        # Cache it
        self.category_cache[app_name] = category
        if self.memory:
            self.memory.save_category(app_name, category)

        return category

    def _simple_categorize(self, app_name: str) -> str:
        """Simple rule-based categorization fallback"""
        app_lower = app_name.lower()

        if any(x in app_lower for x in ['chrome', 'firefox', 'edge', 'browser']):
            return 'web-browsing'
        elif any(x in app_lower for x in ['code', 'visual studio', 'pycharm', 'sublime', 'vim', 'notepad++']):
            return 'coding'
        elif any(x in app_lower for x in ['discord', 'slack', 'teams', 'zoom']):
            return 'communication'
        elif any(x in app_lower for x in ['spotify', 'music', 'vlc', 'media']):
            return 'entertainment'
        elif any(x in app_lower for x in ['game', 'steam', 'epic']):
            return 'gaming'
        elif any(x in app_lower for x in ['word', 'excel', 'powerpoint', 'office']):
            return 'productivity'
        else:
            return 'unknown'

    def stop(self):
        print("Stopping worker...")
        self.running = False


# ============================================================================
# STT WORKER - Handles speech recognition
# ============================================================================

class STTWorker(QThread):
    """Runs speech recognition in separate thread"""
    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def run(self):
        recognizer = sr.Recognizer()

        try:
            with sr.Microphone() as source:
                print("🎤 Listening...")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)

            print("Processing speech...")
            text = recognizer.recognize_google(audio)
            if text:
                print(f"Recognized: {text}")
                self.result_ready.emit(text)

        except sr.WaitTimeoutError:
            print("No speech detected (timeout)")
            self.error_occurred.emit("No speech detected")
        except sr.UnknownValueError:
            print("Could not understand audio")
            self.error_occurred.emit("Could not understand")
        except sr.RequestError as e:
            error_msg = f"Speech recognition error: {e}"
            print(error_msg)
            self.error_occurred.emit(error_msg)
        except Exception as e:
            error_msg = f"STT error: {e}"
            print(error_msg)
            self.error_occurred.emit(error_msg)


# ============================================================================
# MAIN GUI - Runs on main thread only
# ============================================================================

class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        # ===== ANIMATION CONFIG =====
        self.animations = {
            "default": (os.path.join(BASE_DIR, "anim", "idle.png"), 32, 32, 10),
            "eat": (os.path.join(BASE_DIR, "anim", "eat.png"), 32, 32, 15),
            "boxDefault": (os.path.join(BASE_DIR, "anim", "boxDefault.png"), 32, 32, 4),
            "boxSleep": (os.path.join(BASE_DIR, "anim", "boxSleep.png"), 32, 32, 4),
            "lie": (os.path.join(BASE_DIR, "anim", "lie.png"), 32, 32, 12),
            "sleep": (os.path.join(BASE_DIR, "anim", "sleep.png"), 32, 32, 4),
            "yawn": (os.path.join(BASE_DIR, "anim", "yawn.png"), 32, 32, 8),
            "angry": (os.path.join(BASE_DIR, "anim", "angry2.png"), 32, 32, 9),
            "angryalt": (os.path.join(BASE_DIR, "anim", "angry1.png"), 32, 32, 4),
        }

        # Load all animations
        self.loaded_animations = {}
        for name, (path, w, h, f) in self.animations.items():
            if os.path.exists(path):
                self.loaded_animations[name] = {
                    "pixmap": QPixmap(path),
                    "frame_width": w,
                    "frame_height": h,
                    "total_frames": f
                }

        # Create placeholder if no animations loaded
        if not self.loaded_animations:
            print("No animation files found! Creating placeholder...")
            placeholder = QPixmap(32, 32)
            placeholder.fill(QColor(100, 100, 100))
            self.loaded_animations["default"] = {
                "pixmap": placeholder,
                "frame_width": 32,
                "frame_height": 32,
                "total_frames": 1
            }

        self.scale = 3  # 32*3 = 96px
        self.current_animation = "default"
        self.current_frame = 0
        self.fps = 8

        # ===== THREADING SETUP =====
        self.pet_worker = PetWorker()
        self.worker_thread = QThread()

        # Move worker to its own thread
        self.pet_worker.moveToThread(self.worker_thread)

        # Connect signals BEFORE starting thread
        self.worker_thread.started.connect(self.pet_worker.run)
        self.pet_worker.data_updated.connect(self.handle_pet_data)
        self.pet_worker.error_occurred.connect(self.handle_worker_error)

        # Start worker thread
        self.worker_thread.start()

        # ===== MESSAGING SYSTEM (replaces dialog.json) =====
        # Initialize agent bridge and messenger
        self.messenger = RandomMessenger()
        self.setup_messaging()

        # Create pet state proxy for personality engine
        class PetAIProxy:
            def __init__(self, worker):
                self.worker = worker
                self._surprised = False
                self._curious = False
                self._activeApp = "Unknown"
                self._last_category = "unknown"
                self.chatHistory = []

            @property
            def surprised(self):
                return self._surprised

            @property
            def curious(self):
                return self._curious

            @property
            def activeApp(self):
                return self._activeApp

            def categorize(self, app):
                return self._last_category

        self.pet_proxy = PetAIProxy(self.pet_worker)

        # ===== CHAT BUBBLE =====
        self.chatBubble = QLabel("", self)
        self.chatBubble.setWordWrap(True)
        self.chatBubble.setStyleSheet("""
            QLabel {
                background-color: white;
                border: 2px solid black;
                border-radius: 12px;
                padding: 6px 8px;
                color: black;
                font-size: 10px;
                font-family: Arial, sans-serif;
            }
        """)
        self.chatBubble.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.chatBubble.hide()

        # Auto-hide timer for chat
        self.chatHideTimer = QTimer(self)
        self.chatHideTimer.setSingleShot(True)
        self.chatHideTimer.timeout.connect(self.chatBubble.hide)

        # ===== CLICK TRACKING =====
        self.click_times = []
        self.clicked = False

        # ===== WINDOW SETUP =====
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Calculate window size
        anim_data = self.loaded_animations[self.current_animation]
        self.sprite_width = anim_data["frame_width"] * self.scale
        self.sprite_height = anim_data["frame_height"] * self.scale

        self.chat_max_width = 350
        self.chat_max_height = 80

        width = self.sprite_width + self.chat_max_width + 30
        height = max(self.sprite_height, self.chat_max_height) + 30
        self.resize(width, height)

        self.move_to_bottom_right()

        # ===== ANIMATION TIMER =====
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_frame)
        self.animation_timer.start(1000 // self.fps)

        # ===== IDLE TIMERS =====
        self.idle_start_time = time.time()
        self.yawn_triggered = False

        # 5 min idle timer
        self.long_idle_timer = QTimer()
        self.long_idle_timer.setSingleShot(True)
        self.long_idle_timer.timeout.connect(self.handle_long_idle)
        self.long_idle_timer.start(5 * 60 * 1000)

        # Lie to sleep timer
        self.lie_sleep_timer = QTimer()
        self.lie_sleep_timer.setSingleShot(True)
        self.lie_sleep_timer.timeout.connect(self.start_sleep_from_lie)

        # Box to sleep timer
        self.box_sleep_timer = QTimer()
        self.box_sleep_timer.setSingleShot(True)
        self.box_sleep_timer.timeout.connect(self.start_box_sleep)

        # STT worker reference
        self.stt_thread = None

    def setup_messaging(self):
        """Initialize agent bridge and messaging system"""
        try:
            parent_dir = os.path.dirname(BASE_DIR)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

            from core.agent_bridge import AgentBridge
            from core.short_memory import ShortTermMemory

            # Create short-term memory for context
            memory = ShortTermMemory(max_items=500)

            # Initialize agent bridge with UI callback
            self.agent_bridge = AgentBridge(
                ui_show_callback=self.showChat,
                messenger_interval=30,
                memory_max_items=500
            )

            print("✓ Messaging system initialized")

        except Exception as e:
            print(f"Warning: Could not initialize messaging system: {e}")
            print("Pet will run without personality messages")
            self.agent_bridge = None

    def move_to_bottom_right(self):
        """Position window at bottom-right of screen"""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        x = screen_geometry.width() - self.width() - 10
        y = screen_geometry.height() - self.height() - 50
        self.move(x, y)

    # ========================================================================
    # ANIMATION SYSTEM
    # ========================================================================

    def update_frame(self):
        """Advance animation frame"""
        if self.current_animation not in self.loaded_animations:
            return

        anim_data = self.loaded_animations[self.current_animation]
        self.current_frame = (self.current_frame + 1) % anim_data["total_frames"]
        self.update()

        # Check for animation end
        if self.current_frame == anim_data["total_frames"] - 1:
            self.on_animation_end()

    def on_animation_end(self):
        """Handle animation cycle completion"""
        if self.current_animation == "boxDefault":
            self.box_sleep_timer.start(1000)
        elif self.current_animation == "lie":
            self.lie_sleep_timer.start(30000)
        elif self.current_animation in ("angry", "angryalt"):
            self.set_animation("default")
            self.clicked = False
            self.click_times.clear()
        elif self.current_animation == "yawn":
            self.set_animation("default")
            self.yawn_triggered = False

    def set_animation(self, name):
        """Change current animation"""
        if name not in self.loaded_animations:
            print(f"Animation '{name}' not found!")
            return
        if name != self.current_animation:
            self.current_animation = name
            self.current_frame = 0
            self.update()

    def paintEvent(self, event):
        """Draw sprite and speech bubble pointer"""
        painter = QPainter(self)

        if self.current_animation not in self.loaded_animations:
            return

        anim_data = self.loaded_animations[self.current_animation]

        # Extract current frame
        frame_rect = QRect(
            self.current_frame * anim_data["frame_width"],
            0,
            anim_data["frame_width"],
            anim_data["frame_height"]
        )
        frame = anim_data["pixmap"].copy(frame_rect)

        # Scale frame
        scaled_frame = frame.scaled(
            anim_data["frame_width"] * self.scale,
            anim_data["frame_height"] * self.scale,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        # Draw sprite at bottom-right
        sprite_x = self.width() - scaled_frame.width() - 10
        sprite_y = self.height() - scaled_frame.height() - 10
        painter.drawPixmap(sprite_x, sprite_y, scaled_frame)

        # Draw speech pointer if chat visible
        if self.chatBubble.isVisible():
            self.draw_speech_pointer(painter)

    def draw_speech_pointer(self, painter):
        """Draw triangular pointer from bubble to cat"""
        bubble_rect = self.chatBubble.geometry()

        pointer_start_x = bubble_rect.right() - 15
        pointer_start_y = bubble_rect.bottom()

        triangle = QPolygon([
            QPoint(pointer_start_x, pointer_start_y),
            QPoint(pointer_start_x + 15, pointer_start_y + 12),
            QPoint(pointer_start_x - 5, pointer_start_y + 8)
        ])

        painter.setBrush(QBrush(Qt.white))
        painter.setPen(Qt.black)
        painter.drawPolygon(triangle)

    # ========================================================================
    # CHAT SYSTEM
    # ========================================================================

    def truncate_text(self, text, max_width):
        """Truncate text to fit within max_width"""
        font_metrics = self.chatBubble.fontMetrics()

        if font_metrics.boundingRect(text).width() <= max_width:
            return text

        # Try to shorten intelligently
        words = text.split()
        if len(words) > 1:
            shortened_words = []
            for word in words:
                if len(word) > 15:
                    if " - " in text:
                        shortened_words.extend(text.split(" - ")[0].split())
                        break
                    elif "edition" in word.lower():
                        shortened_words.append(word.replace("edition", "ed."))
                    elif "development" in word.lower():
                        shortened_words.append(word.replace("development", "dev"))
                    else:
                        shortened_words.append(word[:12] + "...")
                else:
                    shortened_words.append(word)
            text = " ".join(shortened_words)

        # Final truncation
        while font_metrics.boundingRect(text + "...").width() > max_width and len(text) > 3:
            text = text[:-1]

        return text + "..." if len(text) > 3 else text

    def showChat(self, text, duration=4000):
        """Display chat bubble - called by messaging system"""
        print(f"💬 Chat: {text}")

        available_width = self.chat_max_width - 20
        truncated_text = self.truncate_text(text, available_width)

        self.chatBubble.setText(truncated_text)
        self.chatBubble.setMaximumWidth(self.chat_max_width)
        self.chatBubble.setMaximumHeight(self.chat_max_height)
        self.chatBubble.adjustSize()

        bubble_x = 20
        bubble_y = 20

        self.chatBubble.move(bubble_x, bubble_y)
        self.chatBubble.raise_()
        self.chatBubble.show()

        self.update()  # Redraw to show pointer

        self.chatHideTimer.start(duration)

    # ========================================================================
    # IDLE BEHAVIOR
    # ========================================================================

    def handle_long_idle(self):
        """Trigger after 5 minutes of no interaction"""
        choice = random.choice(["boxSequence", "lieSequence"])
        if choice == "boxSequence" and "boxDefault" in self.loaded_animations:
            self.set_animation("boxDefault")
        elif "lie" in self.loaded_animations:
            self.set_animation("lie")

    def start_sleep_from_lie(self):
        """Lie → sleep transition"""
        if self.current_animation == "lie" and "sleep" in self.loaded_animations:
            self.set_animation("sleep")

    def start_box_sleep(self):
        """BoxDefault → boxSleep transition"""
        if self.current_animation == "boxDefault" and "boxSleep" in self.loaded_animations:
            self.set_animation("boxSleep")

    def reset_idle(self):
        """Reset idle timers on user interaction"""
        self.idle_start_time = time.time()
        self.yawn_triggered = False
        self.long_idle_timer.start(5 * 60 * 1000)

    # ========================================================================
    # INPUT HANDLING
    # ========================================================================

    def mousePressEvent(self, event):
        """Handle mouse clicks"""
        now = time.time()

        # Track clicks
        self.click_times.append(now)
        self.click_times = [t for t in self.click_times if now - t <= 2]

        # Spam clicking = angry
        if len(self.click_times) >= 5:
            angry_options = [a for a in ["angry", "angryalt"] if a in self.loaded_animations]
            if angry_options:
                angry_choice = random.choice(angry_options)
                self.set_animation(angry_choice)
            self.click_times.clear()
            self.clicked = False
            self.reset_idle()
            return

        # First click = STT
        if len(self.click_times) == 1:
            print("🎤 Starting STT...")
            self.start_stt()

        # Normal click
        self.clicked = not self.clicked
        self.set_animation("default")
        self.reset_idle()

    def start_stt(self):
        """Start STT worker thread"""
        if self.stt_thread and self.stt_thread.isRunning():
            print("STT already running, ignoring...")
            return

        self.stt_thread = STTWorker()
        self.stt_thread.result_ready.connect(self.handle_stt_result)
        self.stt_thread.error_occurred.connect(self.handle_stt_error)
        self.stt_thread.start()

    def handle_stt_result(self, text):
        """Process speech recognition result"""
        print(f"Heard: {text}")

        # Send to agent bridge if available
        if self.agent_bridge:
            try:
                self.agent_bridge.handle({
                    "type": "STT_COMMAND",
                    "text": text
                })
            except Exception as e:
                print(f"Agent bridge error: {e}")
        else:
            # Fallback to direct STT command processing
            try:
                parent_dir = os.path.dirname(BASE_DIR)
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)

                from core import STT
                STT.command(text)
            except Exception as e:
                print(f"STT command processing error: {e}")
                self.showChat(f"Error: {e}", 3000)

    def handle_stt_error(self, error_msg):
        """Handle STT errors"""
        print(f"STT Error: {error_msg}")

    # ========================================================================
    # THREAD COMMUNICATION
    # ========================================================================

    def handle_pet_data(self, data):
        """Receive updates from worker thread (runs on GUI thread)"""
        print(f"📊 Pet data: {data}")

        # Update proxy with latest data
        self.pet_proxy._surprised = data.get('surprised', False)
        self.pet_proxy._curious = data.get('curious', False)
        self.pet_proxy._activeApp = data.get('activeApp', 'Unknown')
        self.pet_proxy._last_category = data.get('category', 'unknown')

    def handle_worker_error(self, error_msg):
        """Handle errors from worker thread"""
        print(f"❌ Worker error: {error_msg}")
        self.showChat("Oops, something went wrong!", 3000)

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def closeEvent(self, event):
        """Graceful shutdown"""
        print("🛑 Shutting down...")

        # Stop timers
        self.animation_timer.stop()
        self.long_idle_timer.stop()
        self.lie_sleep_timer.stop()
        self.box_sleep_timer.stop()
        self.chatHideTimer.stop()

        # Stop agent bridge
        if self.agent_bridge:
            try:
                self.agent_bridge.stop(wait=True, timeout=3.0)
            except Exception as e:
                print(f"Error stopping agent bridge: {e}")

        # Stop STT if running
        if self.stt_thread and self.stt_thread.isRunning():
            self.stt_thread.terminate()
            self.stt_thread.wait(1000)

        # Stop worker thread
        self.pet_worker.stop()
        self.worker_thread.quit()
        if not self.worker_thread.wait(5000):
            print("Worker thread didn't stop gracefully, terminating...")
            self.worker_thread.terminate()
            self.worker_thread.wait(1000)

        event.accept()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    # Enable high DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    try:
        pet_gui = DesktopPet()
        pet_gui.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)