import sys
import random
import time
from PyQt5.QtCore import Qt, QTimer, QRect, QObject, pyqtSignal, QThread
from PyQt5.QtGui import QPainter, QPixmap, QFontMetrics
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtGui import QScreen
from petML import PetAI
#from STT import i didnt make it object oriented so im going to stop here and implment STT tmrw or later today
import os
import json
from personalityEngine import Personality


# Sadly most of the gui is Ai as im new to PyQt5
# as time goes on ill replace it while i learn.
#class STTWorker(QObject):
#    data_updated = pyqtSignal(dict)

    #def __init__(self):
    #    super().__init__()
    #    self.running = True

class PetAIWorker(QObject):
    data_updated = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.running = True
        self.pet_ai = PetAI()
        self.pet_ai.load_from_file()
        self.last_saved_count = len(self.pet_ai.chatHistory)

    def run(self):
        while self.running:
            self.pet_ai.app_Tracking()
            self.pet_ai.model()  # <-- Add this so model gets called

            self.data_updated.emit({
                "surprised": self.pet_ai.surprised,
                "curious": self.pet_ai.curious,
                "activeApp": self.pet_ai.activeApp
            })

            current_count = len(self.pet_ai.chatHistory)
            if current_count > self.last_saved_count and current_count >= self.last_saved_count + 1:
                self.pet_ai.train_Model_On_History()
                # self.pet_ai.saveToFile()
                self.last_saved_count = current_count

            time.sleep(5)

    def stop(self):
        self.running = False



class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        # === Config ===
        self.animations = {
            "default": ("anim/idle.png", 32, 32, 10),
            "eat": ("anim/eat.png", 32, 32, 15),
            "boxDefault": ("anim/boxDefault.png", 32, 32, 4),
            "boxSleep": ("anim/boxSleep.png", 32, 32, 4),
            "lie": ("anim/lie.png", 32, 32, 12),
            "sleep": ("anim/sleep.png", 32, 32, 4),
            "yawn": ("anim/yawn.png", 32, 32, 8),
            "angry": ("anim/angry2.png", 32, 32, 9),
            "angryalt": ("anim/angry1.png", 32, 32, 4),
        }
        self.loaded_animations = {}
        for name, (path, w, h, f) in self.animations.items():
            self.loaded_animations[name] = {
                "pixmap": QPixmap(path),
                "frame_width": w,
                "frame_height": h,
                "total_frames": f
            }

        self.scale = 3  # scale factor (32 * 3 = 96)
        self.current_animation = "default"
        self.current_frame = 0
        self.fps = 8

        self.pet_worker = PetAIWorker()
        self.thread = QThread()
        self.pet_worker.moveToThread(self.thread)
        self.thread.started.connect(self.pet_worker.run)
        self.pet_worker.data_updated.connect(self.handle_pet_data)
        self.thread.start()

        # Load dialog lines
        with open("dialog.json", "r", encoding="utf-8") as f:
            moodLines = json.load(f)

        self.personality = Personality(self.pet_worker.pet_ai, self, moodLines)

        # text bubble - with speech bubble styling and pointer
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

        # auto hide timer
        self.chatHideTimer = QTimer(self)
        self.chatHideTimer.setSingleShot(True)
        self.chatHideTimer.timeout.connect(self.chatBubble.hide)

        # Click tracking for angry animation trigger
        self.click_times = []
        self.clicked = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Calculate initial window size - make it more compact
        anim_data = self.loaded_animations[self.current_animation]
        self.sprite_width = anim_data["frame_width"] * self.scale
        self.sprite_height = anim_data["frame_height"] * self.scale

        self.chat_max_width = 350
        self.chat_max_height = 80

        # Much more compact window - just enough space for both elements
        width = self.sprite_width + self.chat_max_width + 30  # Small padding
        height = max(self.sprite_height, self.chat_max_height) + 30  # Height of taller element + padding
        self.resize(width, height)

        self.move_to_bottom_right()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(1000 // self.fps)

        # Idle timers
        self.idle_start_time = time.time()
        self.yawn_triggered = False
        self.long_idle_timer = QTimer()
        self.long_idle_timer.setSingleShot(True)
        self.long_idle_timer.timeout.connect(self.handle_long_idle)
        self.long_idle_timer.start(5 * 60 * 1000)  # 5 minutes idle

        # Lie-to-sleep timer (30 sec wait before sleep)
        self.lie_sleep_timer = QTimer()
        self.lie_sleep_timer.setSingleShot(True)
        self.lie_sleep_timer.timeout.connect(self.start_sleep_from_lie)

        # BoxDefault-to-boxSleep timer (set when boxDefault animation ends)
        self.box_sleep_timer = QTimer()
        self.box_sleep_timer.setSingleShot(True)
        self.box_sleep_timer.timeout.connect(self.start_box_sleep)

    def move_to_bottom_right(self):
        screen: QScreen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        x = screen_geometry.width() - self.width() - 10
        y = screen_geometry.height() - self.height() - 50
        self.move(x, y)

    def update_frame(self):
        anim_data = self.loaded_animations[self.current_animation]
        self.current_frame = (self.current_frame + 1) % anim_data["total_frames"]
        self.update()

        # When an animation cycle finishes, check for triggers
        if self.current_frame == anim_data["total_frames"] - 1:
            self.on_animation_end()

    def on_animation_end(self):
        # Handle special sequences
        if self.current_animation == "boxDefault":
            # After boxDefault ends, start boxSleep after short delay
            self.box_sleep_timer.start(1000)  # 1 second delay before boxSleep
        elif self.current_animation == "lie":
            # After lie ends, wait 30s then sleep
            self.lie_sleep_timer.start(30000)  # 30 seconds
        elif self.current_animation in ("angry", "angryalt"):
            # After angry anim finishes, go back to default and reset click state
            self.set_animation("default")
            self.clicked = False
            self.click_times.clear()
        elif self.current_animation == "yawn":
            # After yawn, go back to default and reset yawning flag
            self.set_animation("default")
            self.yawn_triggered = False

    def paintEvent(self, event):
        painter = QPainter(self)
        anim_data = self.loaded_animations[self.current_animation]

        frame_rect = QRect(
            self.current_frame * anim_data["frame_width"],
            0,
            anim_data["frame_width"],
            anim_data["frame_height"]
        )
        frame = anim_data["pixmap"].copy(frame_rect)

        scaled_frame = frame.scaled(anim_data["frame_width"] * self.scale,
                                    anim_data["frame_height"] * self.scale,
                                    Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation)

        # Position sprite at bottom right of window
        sprite_x = self.width() - scaled_frame.width() - 10
        sprite_y = self.height() - scaled_frame.height() - 10
        painter.drawPixmap(sprite_x, sprite_y, scaled_frame)

        # Draw speech bubble pointer if chat bubble is visible
        if self.chatBubble.isVisible():
            self.draw_speech_pointer(painter)

    def draw_speech_pointer(self, painter):
        """Draw a triangular pointer from the chat bubble toward the cat"""
        # Get bubble position and size
        bubble_rect = self.chatBubble.geometry()

        # Calculate pointer position - from bottom right of bubble toward cat
        pointer_start_x = bubble_rect.right() - 15
        pointer_start_y = bubble_rect.bottom()

        # Create triangle pointing toward cat (roughly)
        from PyQt5.QtGui import QPolygon, QBrush
        from PyQt5.QtCore import QPoint

        triangle = QPolygon([
            QPoint(pointer_start_x, pointer_start_y),
            QPoint(pointer_start_x + 15, pointer_start_y + 12),
            QPoint(pointer_start_x - 5, pointer_start_y + 8)
        ])

        # Draw the pointer with same styling as bubble
        painter.setBrush(QBrush(Qt.white))
        painter.setPen(Qt.black)
        painter.drawPolygon(triangle)

    def set_animation(self, name):
        if name not in self.loaded_animations:
            print(f"Animation '{name}' not found!")
            return
        if name != self.current_animation:
            self.current_animation = name
            self.current_frame = 0
            # Window size doesn't need to change since we reserved space
            self.update()

    def truncate_text(self, text, max_width):
        """Truncate text to fit within max_width, adding ellipsis if needed"""
        font_metrics = self.chatBubble.fontMetrics()

        # If text fits, return as-is
        if font_metrics.boundingRect(text).width() <= max_width:
            return text

        # Try to truncate long app names intelligently
        words = text.split()
        if len(words) > 1:
            # Look for common patterns to shorten
            shortened_words = []
            for word in words:
                if len(word) > 15:  # Very long words
                    if " - " in text:  # App name with tab title
                        # Take first part before dash
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

        # Final truncation if still too long
        while font_metrics.boundingRect(text + "...").width() > max_width and len(text) > 3:
            text = text[:-1]

        return text + "..." if text != text else text

    def showChat(self, text, duration=4000):
        print(f"showChat called with text: {text}")

        # Truncate text if needed
        available_width = self.chat_max_width - 20  # Account for padding
        truncated_text = self.truncate_text(text, available_width)

        self.chatBubble.setText(truncated_text)

        # Set maximum size for the bubble
        self.chatBubble.setMaximumWidth(self.chat_max_width)
        self.chatBubble.setMaximumHeight(self.chat_max_height)

        # Adjust size to content
        self.chatBubble.adjustSize()

        # Position bubble at top-left with small margin
        bubble_x = 20
        bubble_y = 0

        self.chatBubble.move(bubble_x, bubble_y)
        self.chatBubble.raise_()
        self.chatBubble.show()

        # Force a repaint to show the speech pointer
        self.update()

        self.chatHideTimer.start(duration)

    def handle_long_idle(self):
        # Randomly choose the long idle sequence
        choice = random.choice(["boxSequence", "lieSequence"])
        if choice == "boxSequence":
            self.set_animation("boxDefault")
        else:
            self.set_animation("lie")

    def start_sleep_from_lie(self):
        # Called 30s after lie animation finishes
        if self.current_animation == "lie":
            self.set_animation("sleep")

    def start_box_sleep(self):
        # Called 1s after boxDefault animation finishes
        if self.current_animation == "boxDefault":
            self.set_animation("boxSleep")

    def mousePressEvent(self, event):
        now = time.time()
        # Record click time
        self.click_times.append(now)
        # Remove clicks older than 2 seconds
        self.click_times = [t for t in self.click_times if now - t <= 2]

        if len(self.click_times) >= 5:
            # 5 or more clicks in last 2 seconds → angry animation
            angry_choice = random.choice(["angry", "angryalt"])
            self.set_animation(angry_choice)
            self.click_times.clear()
            self.clicked = False
            # Reset idle timer since user interacted
            self.reset_idle()
            return

        self.clicked = not self.clicked
        self.set_animation("default")
        self.reset_idle()

    # Normal click toggles clicked bool and returns to default animation
    def reset_idle(self):
        self.idle_start_time = time.time()
        self.yawn_triggered = False
        # Restart 5 minute idle timer
        self.long_idle_timer.start(5 * 60 * 1000)

    def handle_pet_data(self, data):
        print(f"PetAI data update: {data}")
        self.personality.randomTalk()

    def closeEvent(self, event):
        print("GUI closing — stopping PetAI")
        self.pet_worker.stop()
        self.thread.quit()
        self.thread.wait()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    pet_gui = DesktopPet()
    pet_gui.show()
    sys.exit(app.exec_())