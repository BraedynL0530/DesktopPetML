import random
import time
import os, sys
import traceback
import subprocess
import threading

from PyQt5.QtCore import Qt, QTimer, QRect, QObject, pyqtSignal, QThread, QPoint
from PyQt5.QtGui import QPainter, QPixmap, QPolygon, QBrush, QColor, QFont, QKeySequence
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                             QShortcut, QHBoxLayout, QVBoxLayout, QFrame)

# Global OS-level hotkey hook (works even when a game has focus)
# Install with: pip install keyboard
try:
    import keyboard as _keyboard
    _KEYBOARD_AVAILABLE = True
except ImportError:
    _KEYBOARD_AVAILABLE = False
    print("Warning: 'keyboard' library not found. Kill hotkey won't work across apps.\n"
          "Install with: pip install keyboard")

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
# LAUNCHER OVERLAY  —  shown once at startup
# ============================================================================

class LauncherOverlay(QWidget):
    """
    Floating pill-shaped launcher that appears at startup.
    User picks what to run, then it fades away.
    Hotkey to quit: Ctrl+Shift+F4  (weird enough to not conflict with games)
    """
    launch_pet       = pyqtSignal()
    launch_minecraft = pyqtSignal()
    launch_both      = pyqtSignal()
    quit_requested   = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(340, 180)

        # ── Background frame ──────────────────────────────────────────────
        self.bg = QFrame(self)
        self.bg.setGeometry(0, 0, 340, 180)
        self.bg.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 18, 24, 230);
                border-radius: 18px;
                border: 1px solid rgba(120, 120, 160, 120);
            }
        """)

        # ── Title ─────────────────────────────────────────────────────────
        title = QLabel("🐾  Launch", self.bg)
        title.setFont(QFont("Arial", 13, QFont.Bold))
        title.setStyleSheet("color: rgba(220,220,255,220); background: transparent;")
        title.move(20, 14)

        hint = QLabel("Ctrl+Shift+F4 to quit anytime", self.bg)
        hint.setFont(QFont("Arial", 7))
        hint.setStyleSheet("color: rgba(150,150,180,160); background: transparent;")
        hint.move(20, 38)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_style = """
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border-radius: 10px;
                border: none;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {press};
            }}
        """

        self.btn_pet = QPushButton("🐱  Desktop Pet", self.bg)
        self.btn_pet.setFixedSize(140, 36)
        self.btn_pet.move(20, 68)
        self.btn_pet.setStyleSheet(btn_style.format(
            bg="#3a3a5c", fg="white", hover="#4e4e7a", press="#2a2a44"))

        self.btn_mc = QPushButton("⛏  Minecraft", self.bg)
        self.btn_mc.setFixedSize(140, 36)
        self.btn_mc.move(180, 68)
        self.btn_mc.setStyleSheet(btn_style.format(
            bg="#2d5a3d", fg="white", hover="#3d7a52", press="#1d3a27"))

        self.btn_both = QPushButton("✨  Both", self.bg)
        self.btn_both.setFixedSize(300, 36)
        self.btn_both.move(20, 116)
        self.btn_both.setStyleSheet(btn_style.format(
            bg="#4a2d5a", fg="white", hover="#6a3d7a", press="#2a1a3a"))

        # ── Connections ───────────────────────────────────────────────────
        self.btn_pet.clicked.connect(lambda: (self.launch_pet.emit(),  self.close()))
        self.btn_mc.clicked.connect( lambda: (self.launch_minecraft.emit(), self.close()))
        self.btn_both.clicked.connect(lambda: (self.launch_both.emit(), self.close()))

        # Kill hotkey is registered globally at app startup via register_global_kill_hotkey()

        # ── Position: centre of screen ────────────────────────────────────
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2
        )

    # Allow dragging the launcher around
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and hasattr(self, '_drag_pos'):
            self.move(e.globalPos() - self._drag_pos)


# ============================================================================
# MINECRAFT BRIDGE THREAD  —  starts/stops Flask HTTP server
# ============================================================================

class MinecraftBridgeThread(QThread):
    """Runs the MinecraftBridge HTTP server in its own QThread."""
    started_ok  = pyqtSignal()
    error_out   = pyqtSignal(str)

    def run(self):
        try:
            from minecraft.minecraft_bridge import MinecraftBridge
            self.bridge = MinecraftBridge()
            self.bridge.start()          # starts Flask in an inner daemon thread
            self.started_ok.emit()
            # Keep this QThread alive so the bridge daemon doesn't die
            while not self.isInterruptionRequested():
                time.sleep(1)
        except Exception as e:
            self.error_out.emit(str(e))


# ============================================================================
# WORKER THREAD
# ============================================================================

class PetWorker(QObject):
    data_updated  = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, pet_only: bool = False):
        super().__init__()
        self.running  = False
        self._pet_only = pet_only       # if True, skip tracking Minecraft windows
        self.memory       = Memory()
        self.tracker      = AppTracker()
        self.agent_bridge = AgentBridge()
        self.platform     = PlatformHelper()
        self.category_cache = {}

    def start_worker(self):
        try:
            parent_dir = os.path.dirname(BASE_DIR)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

            self.memory  = Memory()
            self.tracker = AppTracker()
            self.category_cache = self.memory.get_all_categories()

            history = self.memory.get_all_sessions()
            if len(history) >= 10:
                self.tracker.train_on_history(history)

            self.running = True
            print("✓ Worker initialized")
        except Exception as e:
            self.error_occurred.emit(f"Worker init failed: {e}\n{traceback.format_exc()}")

    def run(self):
        self.start_worker()
        if not self.running:
            return

        last_retrain = 0
        error_count  = 0

        while self.running:
            try:
                app_name = self.platform.get_active_app()
                if not app_name:
                    time.sleep(5)
                    continue

                # In pet_only mode skip Minecraft windows entirely
                if self._pet_only and 'minecraft' in app_name.lower():
                    time.sleep(5)
                    continue

                session = self.tracker.start_tracking(app_name)
                if session:
                    category = self.get_category(session['app'])
                    session['category'] = category
                    self.memory.save_session(session)
                    self.tracker.predict_anomalies(session, category)

                current_category = self.get_category(app_name)
                self.data_updated.emit({
                    'surprised': self.tracker.surprised,
                    'curious':   self.tracker.curious,
                    'activeApp': app_name,
                    'category':  current_category
                })

                if self.memory:
                    count = self.memory.get_session_count()
                    if count > 0 and count % 50 == 0 and count != last_retrain:
                        history = self.memory.get_all_sessions()
                        if self.tracker.train_on_history(history):
                            last_retrain = count

                error_count = 0
                time.sleep(5)

            except Exception as e:
                error_count += 1
                if error_count >= 10:
                    self.error_occurred.emit("Worker hit error limit")
                    break
                time.sleep(1)

    def get_category(self, app_name: str) -> str:
        if not app_name:
            return 'unknown'
        if app_name in self.category_cache:
            return self.category_cache[app_name]
        if self.memory:
            category = self.memory.get_category(app_name)
            if category != 'unknown':
                self.category_cache[app_name] = category
                return category
        category = self._simple_categorize(app_name)
        self.category_cache[app_name] = category
        if self.memory:
            self.memory.save_category(app_name, category)
        return category

    def _simple_categorize(self, app_name: str) -> str:
        app_lower = app_name.lower()
        if any(x in app_lower for x in ['chrome', 'firefox', 'edge', 'browser']):
            return 'web-browsing'
        elif any(x in app_lower for x in ['code', 'visual studio', 'pycharm', 'sublime', 'vim', 'notepad++']):
            return 'coding'
        elif any(x in app_lower for x in ['discord', 'slack', 'teams', 'zoom']):
            return 'communication'
        elif any(x in app_lower for x in ['spotify', 'music', 'vlc', 'media']):
            return 'entertainment'
        elif any(x in app_lower for x in ['game', 'steam', 'epic', 'minecraft']):
            return 'gaming'
        elif any(x in app_lower for x in ['word', 'excel', 'powerpoint', 'office']):
            return 'productivity'
        return 'unknown'

    def stop(self):
        self.running = False


# ============================================================================
# STT WORKER
# ============================================================================

class STTWorker(QThread):
    result_ready   = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def run(self):
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            text = recognizer.recognize_google(audio)
            if text:
                self.result_ready.emit(text)
        except sr.WaitTimeoutError:
            self.error_occurred.emit("No speech detected")
        except sr.UnknownValueError:
            self.error_occurred.emit("Could not understand")
        except sr.RequestError as e:
            self.error_occurred.emit(f"Speech recognition error: {e}")
        except Exception as e:
            self.error_occurred.emit(f"STT error: {e}")


# ============================================================================
# MAIN GUI
# ============================================================================

class DesktopPet(QWidget):
    chat_signal = pyqtSignal(str)

    def __init__(self, start_minecraft_bridge: bool = False, pet_only: bool = False):
        super().__init__()

        # If pet_only=True the worker skips tracking Minecraft windows
        self._pet_only = pet_only

        # ── Minecraft bridge (optional) ───────────────────────────────────
        self.mc_bridge_thread = None
        if start_minecraft_bridge:
            self._start_minecraft_bridge()

        # ── Animations ────────────────────────────────────────────────────
        self.animations = {
            "default":    (os.path.join(BASE_DIR, "anim", "idle.png"),        32, 32, 10),
            "eat":        (os.path.join(BASE_DIR, "anim", "eat.png"),         32, 32, 15),
            "boxDefault": (os.path.join(BASE_DIR, "anim", "boxDefault.png"),  32, 32,  4),
            "boxSleep":   (os.path.join(BASE_DIR, "anim", "boxSleep.png"),    32, 32,  4),
            "lie":        (os.path.join(BASE_DIR, "anim", "lie.png"),         32, 32, 12),
            "sleep":      (os.path.join(BASE_DIR, "anim", "sleep.png"),       32, 32,  4),
            "yawn":       (os.path.join(BASE_DIR, "anim", "yawn.png"),        32, 32,  8),
            "angry":      (os.path.join(BASE_DIR, "anim", "angry2.png"),      32, 32,  9),
            "angryalt":   (os.path.join(BASE_DIR, "anim", "angry1.png"),      32, 32,  4),
        }

        self.loaded_animations = {}
        for name, (path, w, h, f) in self.animations.items():
            if os.path.exists(path):
                self.loaded_animations[name] = {
                    "pixmap": QPixmap(path), "frame_width": w,
                    "frame_height": h, "total_frames": f
                }

        if not self.loaded_animations:
            placeholder = QPixmap(32, 32)
            placeholder.fill(QColor(100, 100, 100))
            self.loaded_animations["default"] = {
                "pixmap": placeholder, "frame_width": 32,
                "frame_height": 32, "total_frames": 1
            }

        self.scale             = 3
        self.current_animation = "default"
        self.current_frame     = 0
        self.fps               = 8

        # ── Worker thread ─────────────────────────────────────────────────
        self.pet_worker    = PetWorker(pet_only=pet_only)
        self.worker_thread = QThread()
        self.pet_worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.pet_worker.run)
        self.pet_worker.data_updated.connect(self.handle_pet_data)
        self.pet_worker.error_occurred.connect(self.handle_worker_error)
        self.worker_thread.start()
        self.chat_signal.connect(self.showChat)

        # ── Messaging ─────────────────────────────────────────────────────
        self.setup_messaging()

        class PetAIProxy:
            def __init__(self, worker):
                self.worker = worker
                self._surprised = False
                self._curious   = False
                self._activeApp = "Unknown"
                self._last_category = "unknown"
                self.chatHistory = []
            @property
            def surprised(self): return self._surprised
            @property
            def curious(self):   return self._curious
            @property
            def activeApp(self): return self._activeApp
            def categorize(self, app): return self._last_category

        self.pet_proxy = PetAIProxy(self.pet_worker)

        # ── Chat bubble ───────────────────────────────────────────────────
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

        self.chatHideTimer = QTimer(self)
        self.chatHideTimer.setSingleShot(True)
        self.chatHideTimer.timeout.connect(self.chatBubble.hide)

        # ── Minecraft status indicator (small dot) ────────────────────────
        self.mc_indicator = QLabel("⛏", self)
        self.mc_indicator.setFont(QFont("Arial", 9))
        self.mc_indicator.setStyleSheet(
            "color: rgba(100,100,100,180); background: transparent;")
        self.mc_indicator.setFixedSize(20, 20)
        self.mc_indicator.hide()

        # ── Click tracking ────────────────────────────────────────────────
        self.click_times = []
        self.clicked     = False

        # ── Window setup ──────────────────────────────────────────────────
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        anim_data = self.loaded_animations[self.current_animation]
        self.sprite_width  = anim_data["frame_width"]  * self.scale
        self.sprite_height = anim_data["frame_height"] * self.scale
        self.chat_max_width  = 350
        self.chat_max_height =  80

        self.resize(self.sprite_width + self.chat_max_width + 30,
                    max(self.sprite_height, self.chat_max_height) + 30)
        self.move_to_bottom_right()

        # Position mc indicator top-left of sprite
        self.mc_indicator.move(
            self.width() - self.sprite_width - 10,
            self.height() - self.sprite_height - 10
        )

        # ── Timers ────────────────────────────────────────────────────────
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_frame)
        self.animation_timer.start(1000 // self.fps)

        self.idle_start_time = time.time()
        self.yawn_triggered  = False

        self.long_idle_timer = QTimer()
        self.long_idle_timer.setSingleShot(True)
        self.long_idle_timer.timeout.connect(self.handle_long_idle)
        self.long_idle_timer.start(5 * 60 * 1000)

        self.lie_sleep_timer = QTimer()
        self.lie_sleep_timer.setSingleShot(True)
        self.lie_sleep_timer.timeout.connect(self.start_sleep_from_lie)

        self.box_sleep_timer = QTimer()
        self.box_sleep_timer.setSingleShot(True)
        self.box_sleep_timer.timeout.connect(self.start_box_sleep)

        self.stt_thread = None

    # ── Minecraft bridge ──────────────────────────────────────────────────

    def _start_minecraft_bridge(self):
        self.mc_bridge_thread = MinecraftBridgeThread()
        self.mc_bridge_thread.started_ok.connect(self._on_bridge_ready)
        self.mc_bridge_thread.error_out.connect(self._on_bridge_error)
        self.mc_bridge_thread.start()

    def _on_bridge_ready(self):
        print("✓ Minecraft bridge running")
        if hasattr(self, 'mc_indicator'):
            self.mc_indicator.setText("⛏")
            self.mc_indicator.setStyleSheet(
                "color: rgba(80,200,80,220); background: transparent;")
            self.mc_indicator.show()
        # ── Wire bridge into agent_bridge so agents() gets MinecraftAgent ─
        if self.agent_bridge and self.mc_bridge_thread:
            try:
                self.agent_bridge.set_mc_bridge(self.mc_bridge_thread.bridge)
                print("✓ Minecraft bridge wired into agent_bridge")
            except Exception as e:
                print(f"⚠ Could not wire bridge: {e}")
        self.showChat("Minecraft bridge ready! Run /petbot_main setup in-game 🎮", 5000)

    def _on_bridge_error(self, msg):
        print(f"❌ Minecraft bridge error: {msg}")
        self.showChat("Minecraft bridge failed to start 😿", 4000)

    # ── Messaging ─────────────────────────────────────────────────────────

    def setup_messaging(self):
        try:
            from core.agent_bridge import AgentBridge
            from core.short_memory import ShortTermMemory

            def thread_safe_show_chat(text):
                self.chat_signal.emit(text)

            self.agent_bridge = AgentBridge(
                ui_show_callback=thread_safe_show_chat,
                messenger_interval=120,
                memory_max_items=500
            )
            print("✓ Messaging system initialized")
        except Exception as e:
            print(f"Warning: messaging system failed: {e}")
            traceback.print_exc()
            self.agent_bridge = None

    # ── Window helpers ────────────────────────────────────────────────────

    def move_to_bottom_right(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 10,
                  screen.height() - self.height() - 50)

    # ── Animation system ──────────────────────────────────────────────────

    def update_frame(self):
        if self.current_animation not in self.loaded_animations:
            return
        anim_data = self.loaded_animations[self.current_animation]
        self.current_frame = (self.current_frame + 1) % anim_data["total_frames"]
        self.update()
        if self.current_frame == anim_data["total_frames"] - 1:
            self.on_animation_end()

    def on_animation_end(self):
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
        if name not in self.loaded_animations:
            return
        if name != self.current_animation:
            self.current_animation = name
            self.current_frame = 0
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.current_animation not in self.loaded_animations:
            return
        anim_data = self.loaded_animations[self.current_animation]
        frame_rect = QRect(
            self.current_frame * anim_data["frame_width"], 0,
            anim_data["frame_width"], anim_data["frame_height"]
        )
        frame = anim_data["pixmap"].copy(frame_rect)
        scaled_frame = frame.scaled(
            anim_data["frame_width"] * self.scale,
            anim_data["frame_height"] * self.scale,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        sprite_x = self.width()  - scaled_frame.width()  - 10
        sprite_y = self.height() - scaled_frame.height() - 10
        painter.drawPixmap(sprite_x, sprite_y, scaled_frame)
        if self.chatBubble.isVisible():
            self.draw_speech_pointer(painter)

    def draw_speech_pointer(self, painter):
        bubble_rect    = self.chatBubble.geometry()
        pointer_start_x = bubble_rect.right() - 15
        pointer_start_y = bubble_rect.bottom()
        triangle = QPolygon([
            QPoint(pointer_start_x,      pointer_start_y),
            QPoint(pointer_start_x + 15, pointer_start_y + 12),
            QPoint(pointer_start_x - 5,  pointer_start_y + 8)
        ])
        painter.setBrush(QBrush(Qt.white))
        painter.setPen(Qt.black)
        painter.drawPolygon(triangle)

    # ── Chat system ───────────────────────────────────────────────────────

    def truncate_text(self, text, max_width):
        font_metrics = self.chatBubble.fontMetrics()
        if font_metrics.boundingRect(text).width() <= max_width:
            return text
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
        while font_metrics.boundingRect(text + "...").width() > max_width and len(text) > 3:
            text = text[:-1]
        return text + "..." if len(text) > 3 else text

    def showChat(self, text, duration=4000):
        print(f"💬 Chat: {text}")
        available_width  = self.chat_max_width - 20
        truncated_text   = self.truncate_text(text, available_width)
        self.chatBubble.setText(truncated_text)
        self.chatBubble.setMaximumWidth(self.chat_max_width)
        self.chatBubble.setMaximumHeight(self.chat_max_height)
        self.chatBubble.adjustSize()
        self.chatBubble.move(20, 20)
        self.chatBubble.raise_()
        self.chatBubble.show()
        self.update()
        self.chatHideTimer.start(duration)

    # ── Idle behaviour ────────────────────────────────────────────────────

    def handle_long_idle(self):
        choice = random.choice(["boxSequence", "lieSequence"])
        if choice == "boxSequence" and "boxDefault" in self.loaded_animations:
            self.set_animation("boxDefault")
        elif "lie" in self.loaded_animations:
            self.set_animation("lie")

    def start_sleep_from_lie(self):
        if self.current_animation == "lie" and "sleep" in self.loaded_animations:
            self.set_animation("sleep")

    def start_box_sleep(self):
        if self.current_animation == "boxDefault" and "boxSleep" in self.loaded_animations:
            self.set_animation("boxSleep")

    def reset_idle(self):
        self.idle_start_time = time.time()
        self.yawn_triggered  = False
        self.long_idle_timer.start(5 * 60 * 1000)

    # ── Input handling ────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        now = time.time()
        self.click_times.append(now)
        self.click_times = [t for t in self.click_times if now - t <= 2]

        if len(self.click_times) >= 5:
            angry_options = [a for a in ["angry", "angryalt"] if a in self.loaded_animations]
            if angry_options:
                self.set_animation(random.choice(angry_options))
            self.click_times.clear()
            self.clicked = False
            self.reset_idle()
            return

        if len(self.click_times) == 1:
            self.start_stt()

        self.clicked = not self.clicked
        self.set_animation("default")
        self.reset_idle()

    def start_stt(self):
        if self.stt_thread and self.stt_thread.isRunning():
            return
        self.stt_thread = STTWorker()
        self.stt_thread.result_ready.connect(self.handle_stt_result)
        self.stt_thread.error_occurred.connect(self.handle_stt_error)
        self.stt_thread.start()

    def handle_stt_result(self, text):
        print(f"Heard: {text}")
        if self.agent_bridge:
            try:
                self.agent_bridge.handle({"type": "STT_COMMAND", "text": text})
            except Exception as e:
                print(f"Agent bridge error: {e}")
        else:
            try:
                from core import STT
                STT.command(text)
            except Exception as e:
                self.showChat(f"Error: {e}", 3000)

    def handle_stt_error(self, error_msg):
        print(f"STT Error: {error_msg}")

    # ── Thread communication ──────────────────────────────────────────────

    def handle_pet_data(self, data):
        self.pet_proxy._surprised    = data.get('surprised', False)
        self.pet_proxy._curious      = data.get('curious',   False)
        self.pet_proxy._activeApp    = data.get('activeApp', 'Unknown')
        self.pet_proxy._last_category = data.get('category', 'unknown')

        if self.agent_bridge and self.agent_bridge.memory:
            try:
                self.agent_bridge.memory.add("app_activity", {
                    "app":       data.get('activeApp', 'Unknown'),
                    "category":  data.get('category',  'unknown'),
                    "surprised": data.get('surprised', False),
                    "curious":   data.get('curious',   False)
                })
                if hasattr(self.agent_bridge, 'messenger'):
                    m = self.agent_bridge.messenger
                    m.pet._activeApp      = data.get('activeApp', 'Unknown')
                    m.pet._last_category  = data.get('category',  'unknown')
                    m.pet._surprised      = data.get('surprised', False)
                    m.pet._curious        = data.get('curious',   False)
            except Exception as e:
                print(f"Error updating messenger context: {e}")

    def handle_worker_error(self, error_msg):
        print(f"❌ Worker error: {error_msg}")
        self.showChat("Oops, something went wrong!", 3000)

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        print("🛑 Shutting down...")
        self.animation_timer.stop()
        self.long_idle_timer.stop()
        self.lie_sleep_timer.stop()
        self.box_sleep_timer.stop()
        self.chatHideTimer.stop()

        if self.agent_bridge:
            try:
                self.agent_bridge.stop(wait=True, timeout=3.0)
            except Exception as e:
                print(f"Error stopping agent bridge: {e}")

        if self.stt_thread and self.stt_thread.isRunning():
            self.stt_thread.terminate()
            self.stt_thread.wait(1000)

        if self.mc_bridge_thread and self.mc_bridge_thread.isRunning():
            self.mc_bridge_thread.requestInterruption()
            self.mc_bridge_thread.wait(2000)

        self.pet_worker.stop()
        self.worker_thread.quit()
        if not self.worker_thread.wait(5000):
            self.worker_thread.terminate()
            self.worker_thread.wait(1000)

        event.accept()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

# ============================================================================
# GLOBAL KILL HOTKEY  —  works even when a game has focus
# ============================================================================

def register_global_kill_hotkey(app: QApplication):
    """
    Registers Ctrl+Shift+F4 as a system-wide hotkey using the 'keyboard' lib.
    Fires app.quit() via a thread-safe Qt signal.
    Requires: pip install keyboard  (and run as admin on Windows for global hooks)
    """
    if not _KEYBOARD_AVAILABLE:
        print("⚠  Global kill hotkey disabled — install 'keyboard' lib and run as admin.")
        return

    def _on_hotkey():
        print("🔑 Kill hotkey triggered")
        # keyboard callback runs on a background thread; use QTimer to hop to Qt thread
        QTimer.singleShot(0, app.quit)

    try:
        _keyboard.add_hotkey("ctrl+shift+f4", _on_hotkey, suppress=True)
        print("✓ Global kill hotkey registered: Ctrl+Shift+F4")
    except Exception as e:
        print(f"⚠  Could not register global hotkey: {e}\n"
              "   Try running as Administrator.")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Register OS-level kill hotkey immediately (before any window opens)
    register_global_kill_hotkey(app)

    # ── Show launcher ─────────────────────────────────────────────────────
    launcher = LauncherOverlay()

    pet_window = None

    def start_pet(with_minecraft=False):
        global pet_window
        # pet_only=True means the worker ignores Minecraft windows
        pet_window = DesktopPet(
            start_minecraft_bridge=with_minecraft,
            pet_only=not with_minecraft   # tracking off for MC windows when pet-only
        )
        pet_window.show()

    def start_minecraft_only():
        global pet_window
        # Launch bridge; pet_only=False so it still tracks other apps normally
        pet_window = DesktopPet(start_minecraft_bridge=True, pet_only=False)
        pet_window.show()

    launcher.launch_pet.connect(lambda: start_pet(with_minecraft=False))
    launcher.launch_minecraft.connect(start_minecraft_only)
    launcher.launch_both.connect(lambda: start_pet(with_minecraft=True))
    launcher.quit_requested.connect(app.quit)

    launcher.show()

    try:
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)