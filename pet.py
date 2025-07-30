import sys
import random
import time
from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtGui import QScreen


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
        self.fps = 10

        # Click tracking for angry animation trigger
        self.click_times = []
        self.clicked = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        anim_data = self.loaded_animations[self.current_animation]
        self.resize(anim_data["frame_width"] * self.scale, anim_data["frame_height"] * self.scale)

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
        anim_data = self.loaded_animations[self.current_animation]
        w, h = anim_data["frame_width"] * self.scale, anim_data["frame_height"] * self.scale
        x = screen_geometry.width() - w - 10
        y = screen_geometry.height() - h - 50
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

        painter.drawPixmap(0, 0, scaled_frame)

    def set_animation(self, name):
        if name not in self.loaded_animations:
            print(f"Animation '{name}' not found!")
            return
        if name != self.current_animation:
            self.current_animation = name
            self.current_frame = 0
            anim_data = self.loaded_animations[name]
            self.resize(anim_data["frame_width"] * self.scale, anim_data["frame_height"] * self.scale)
            self.move_to_bottom_right()
            self.update()

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
            self.clicked = True
            # Reset idle timer since user interacted
            self.reset_idle()
            return

        # Normal click toggles clicked bool and returns to default animation
        self.clicked = not self.clicked
        self.set_animation("default")
        self.reset_idle()

    def reset_idle(self):
        self.idle_start_time = time.time()
        self.yawn_triggered = False
        # Restart 5 minute idle timer
        self.long_idle_timer.start(5 * 60 * 1000)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()

    sys.exit(app.exec_())
