import os
import random
import logging
import time
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QWidget,
)
from PySide6.QtGui import (
    QPainter,
    QPixmap,
    QImage,
    QFont,
    QFontDatabase,
    QColor,
    QFontMetrics,
)
from PySide6.QtCore import (
    Signal,
    QTimer,
    Qt,
    QPoint,
    QPropertyAnimation,
    QEasingCurve,
    Qt,
    QRect,
    Slot,
    QBuffer,
    QThread
)
from collections import OrderedDict

# 전역 변수로 LRU 캐시 크기 설정
IMAGE_CACHE_SIZE = 20


# LRU 캐시 구현
class LRUCache:
    def __init__(self, capacity=10):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        elif len(self.cache) >= self.capacity:
            self.cache.popitem(last=False)
        self.cache[key] = value


# 이미지 로딩 및 캐싱 함수
def load_and_cache_image(path, cache):
    cached_image = cache.get(path)
    if cached_image is not None:
        return cached_image

    image = QImage(path)
    scaled_image = image.scaled(
        image.width() * 1.5,
        image.height() * 1.5,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )

    # 이미지 압축
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    scaled_image.save(buffer, "PNG", quality=70)  # 압축률 조정 (0-100)
    compressed_image = QImage()
    compressed_image.loadFromData(buffer.data(), "PNG")

    cache.put(path, compressed_image)
    return compressed_image


# 캐릭터 애니메이션 스레드
class CharacterAnimationThread(QThread):
    update_signal = Signal()

    def __init__(self, character_widget):
        super().__init__()
        self.character_widget = character_widget

    def run(self):
        while True:
            time.sleep(0.1)  # 100ms마다 업데이트
            self.update_signal.emit()


class CharacterWidget(QWidget):
    exit_signal = Signal()
    toggle_voice_recognition = Signal()
    set_listening_state_signal = Signal(bool)
    show_speech_bubble_signal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_listening = False
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.offset = QPoint()
        self.animation = None
        self.context_menu = None
        self.is_moving = False
        self.is_dragging = False
        self.current_frame = 0
        self.last_pos = self.pos()

        self.facing_left = False  # 기본적으로 오른쪽을 바라봄
        self.actions = ["idle", "walk", "sit"]
        self.current_action = "idle"

        self.image_cache = {}
        self.falling = False
        self.fall_frame = 0

        self.speech_bubble = None
        self.speech_timer = QTimer(self)
        self.speech_timer.timeout.connect(self.hide_speech_bubble)

        # 폰트 로드
        font_id = QFontDatabase.addApplicationFont("DNFBitBitv2.ttf")
        if font_id != -1:
            self.font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
        else:
            logging.warning(
                "DNFBitBitv2.ttf 폰트를 로드할 수 없습니다. 기본 폰트를 사용합니다."
            )
            self.font_family = QFont().family()

        self.initUI()
        self.load_images()
        self.start_auto_move()

        self.animation_thread = CharacterAnimationThread(self)
        self.animation_thread.update_signal.connect(self.update_animation)
        self.animation_thread.start()

        self.show_speech_bubble_signal.connect(self._show_speech_bubble)

    def initUI(self):
        self.setGeometry(100, 100, 100, 100)

        self.move_timer = QTimer(self)
        self.move_timer.timeout.connect(self.start_random_move)

        self.action_timer = QTimer(self)
        self.action_timer.timeout.connect(self.perform_random_action)

        self.action_duration_timer = QTimer(self)
        self.action_duration_timer.timeout.connect(self.end_current_action)

        self.fall_timer = QTimer(self)
        self.fall_timer.timeout.connect(self.fall)

        self.interaction_timer = QTimer(self)
        self.interaction_timer.timeout.connect(self.interact_with_others)
        self.interaction_timer.start(5000)  # 5초마다 상호작용 시도

        self.set_listening_state_signal.connect(self._set_listening_state)
        self.create_context_menu()

    def create_context_menu(self):
        self.context_menu = QMenu(self)
        sit_action = self.context_menu.addAction("앉기")
        sit_action.triggered.connect(self.sit)
        idle_action = self.context_menu.addAction("기본 상태")
        idle_action.triggered.connect(
            self.return_to_idle
        )  # idle() 대신 return_to_idle() 사용
        fall_action = self.context_menu.addAction("떨어지기")
        fall_action.triggered.connect(self.start_fall)
        exit_action = self.context_menu.addAction("제거")
        exit_action.triggered.connect(self.close)

    def load_images(self):
        image_folder = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "images"
        )
        self.image_sets = {
            "idle": [
                self.load_and_cache_image(os.path.join(image_folder, f"idle{i}.png"))
                for i in range(1, 9)
            ],
            "walk": [
                self.load_and_cache_image(os.path.join(image_folder, f"walk{i}.png"))
                for i in range(1, 10)
            ],
            "drag": [
                self.load_and_cache_image(os.path.join(image_folder, f"drag{i}.png"))
                for i in range(1, 9)
            ],
            "listen": [
                self.load_and_cache_image(os.path.join(image_folder, f"sit{i}.png"))
                for i in range(1, 10)
            ],
            "sit": [
                self.load_and_cache_image(os.path.join(image_folder, f"sit{i}.png"))
                for i in range(1, 10)
            ],
            "fall": [
                self.load_and_cache_image(os.path.join(image_folder, f"fall{i}.png"))
                for i in range(1, 9)
            ],
        }
        self.current_image = self.image_sets["idle"][0]
        self.resize(QPixmap.fromImage(self.current_image).size())

    def load_and_cache_image(self, path):
        if path not in self.image_cache:
            image = QImage(path)
            scaled_image = image.scaled(
                image.width() * 1.5,
                image.height() * 1.5,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.image_cache[path] = scaled_image
        return self.image_cache[path]

    def start_auto_move(self):
        if not self.is_listening:
            self.move_timer.start(random.randint(3000, 10000))

    def stop_auto_move(self):
        self.move_timer.stop()
        if self.animation:
            self.animation.stop()
        self.is_moving = False

    def start_random_move(self):
        if (
            not self.is_dragging
            and not self.is_listening
            and self.current_action != "sit"
            and not self.falling
        ):
            self.animate()

    def animate(self):
        if (
            (
                self.animation is None
                or self.animation.state() == QPropertyAnimation.Stopped
            )
            and not self.is_listening
            and self.current_action != "sit"
            and not self.falling
        ):
            self.animation = QPropertyAnimation(self, b"pos")
            self.animation.setDuration(3000)
            start_pos = self.pos()
            self.animation.setStartValue(start_pos)

            screen = QApplication.primaryScreen().geometry()
            max_distance = 100
            new_x = max(
                0,
                min(
                    start_pos.x() + random.randint(-max_distance, max_distance),
                    screen.width() - self.width(),
                ),
            )
            new_y = max(
                0,
                min(
                    start_pos.y() + random.randint(-max_distance, max_distance),
                    screen.height() - self.height(),
                ),
            )

            self.animation.setEndValue(QPoint(new_x, new_y))
            self.animation.setEasingCurve(QEasingCurve.InOutQuad)
            self.animation.finished.connect(self.animationFinished)
            self.animation.start()
            self.current_action = "walk"
            self.is_moving = True
            self.facing_left = new_x < start_pos.x()

    def animationFinished(self):
        self.is_moving = False
        self.current_action = "idle"
        self.update()

    def update_animation(self):
        action = (
            "fall"
            if self.falling
            else (
                "drag"
                if self.is_dragging
                else (
                    "walk"
                    if self.is_moving and not self.is_listening
                    else (
                        "sit"
                        if self.current_action == "sit" or self.is_listening
                        else "idle"
                    )
                )
            )
        )
        self.current_frame = (self.current_frame + 1) % len(self.image_sets[action])
        self.current_image = self.image_sets[action][self.current_frame]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.facing_left:
            flipped_image = self.current_image.mirrored(True, False)
            painter.drawPixmap(self.rect(), QPixmap.fromImage(flipped_image))
        else:
            painter.drawPixmap(self.rect(), QPixmap.fromImage(self.current_image))

        if self.speech_bubble:
            self.speech_bubble.update_position()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.pos()
            self.is_dragging = True
            self.stop_auto_move()
            if self.current_action == "sit":
                self.return_to_idle()  # 앉아있는 상태에서 드래그 시 idle 상태로 변경
            self.current_image = self.image_sets["drag"][0]
            self.update()
        elif event.button() == Qt.RightButton:
            self.show_context_menu(event.pos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            new_pos = self.mapToParent(event.pos() - self.offset)
            self.move(new_pos)
            self.update_drag_image(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            self.return_to_idle()  # 드래그 종료 시 idle 상태로 변경
            self.start_auto_move()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_fall()

    def update_drag_image(self, new_pos):
        if new_pos.x() < self.last_pos.x():
            self.facing_left = True
        elif new_pos.x() > self.last_pos.x():
            self.facing_left = False
        self.last_pos = new_pos

    def show_context_menu(self, pos):
        self.context_menu.exec_(self.mapToGlobal(pos))

    def closeEvent(self, event):
        self.exit_signal.emit()
        super().closeEvent(event)

    def sit(self):
        self.stop_auto_move()
        self.current_action = "sit"
        self.current_image = self.image_sets["sit"][0]
        self.update()
        self.action_timer.stop()  # 앉아있는 동안 자동 행동 타이머 중지

    def idle(self):
        self.return_to_idle()
        self.start_auto_move()

    def return_to_idle(self):
        self.current_action = "idle"
        self.current_image = self.image_sets["idle"][0]
        self.update()
        self.action_timer.start(random.randint(15000, 45000))  # 자동 행동 타이머 재시작

    def _set_listening_state(self, is_listening):
        self.is_listening = is_listening
        if is_listening:
            self.current_action = "sit"
            self.current_image = self.image_sets["sit"][0]
            self.stop_auto_move()
            self.action_timer.stop()
            self.action_duration_timer.stop()
        else:
            self.current_action = "idle"
            self.current_image = self.image_sets["idle"][0]
            self.start_auto_move()
            self.action_timer.start(random.randint(15000, 45000))
        self.update()

    def set_listening_state(self, is_listening):
        self.set_listening_state_signal.emit(is_listening)

    def perform_random_action(self):
        if (
            not self.is_listening
            and not self.is_dragging
            and self.current_action != "sit"
            and not self.falling
        ):
            action = random.choice(["idle", "walk", "sit"])
            if action == "walk":
                self.start_random_move()
            elif action == "sit":
                self.sit()
                duration = random.randint(3000, 8000)
                self.action_duration_timer.start(duration)
            else:
                self.return_to_idle()  # idle() 대신 return_to_idle() 사용

        if not self.is_listening and self.current_action != "sit" and not self.falling:
            self.action_timer.start(random.randint(15000, 45000))

    def end_current_action(self):
        self.action_duration_timer.stop()
        self.idle()

    def start_fall(self):
        if not self.falling and self.current_action != "sit":
            self.falling = True
            self.stop_auto_move()
            self.fall_frame = 0
            self.fall_timer.start(50)

    def fall(self):
        if not self.falling:
            return

        screen = QApplication.primaryScreen().geometry()
        current_pos = self.pos()
        new_pos = QPoint(current_pos.x(), current_pos.y() + 10)

        if new_pos.y() + self.height() > screen.height():
            self.falling = False
            new_pos.setY(screen.height() - self.height())
            self.current_action = "idle"  # 떨어진 후 idle 상태로 변경
            self.start_auto_move()

        self.move(new_pos)

    def interact_with_others(self):
        if self.parent() and hasattr(self.parent(), "character_widgets"):
            others = [char for char in self.parent().character_widgets if char != self]
            if others:
                target = random.choice(others)
                self.move_towards(target.pos())

    def move_towards(self, target_pos):
        if (
            self.falling
            or self.is_dragging
            or self.is_listening
            or self.current_action == "sit"
        ):
            return

        current_pos = self.pos()
        dx = target_pos.x() - current_pos.x()
        dy = target_pos.y() - current_pos.y()
        distance = (dx**2 + dy**2) ** 0.5

        if distance > 5:
            speed = 5
            ratio = speed / distance
            new_x = current_pos.x() + dx * ratio
            new_y = current_pos.y() + dy * ratio
            self.move(QPoint(int(new_x), int(new_y)))
            self.current_frame = (self.current_frame + 1) % len(self.walk_images)
            self.current_image = self.walk_images[self.current_frame]
            self.facing_left = dx < 0
            self.update()

    @Slot(str)
    def show_speech_bubble(self, text):
        # 메인 스레드에서 실행되도록 시그널 발생
        self.show_speech_bubble_signal.emit(text)

    @Slot(str)
    def _show_speech_bubble(self, text):
        if self.speech_bubble:
            self.speech_bubble.hide()

        self.speech_bubble = SpeechBubble(text, self)
        self.speech_bubble.show()

        # 말풍선이 부모 위젯의 레이아웃에 의해 가려지지 않도록 최상위 레벨로 올림
        self.speech_bubble.raise_()

        # 말풍선이 제대로 표시되도록 강제로 업데이트
        self.speech_bubble.update()
        self.update()

    @Slot()
    def hide_speech_bubble(self):
        if self.speech_bubble:
            self.speech_bubble.hide()
            self.speech_bubble = None


class SpeechBubble(QWidget):
    def __init__(self, text, parent):
        super().__init__(parent)
        self.text = text
        self.parent = parent
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.font = QFont(parent.font_family, 12)
        self.fm = QFontMetrics(self.font)
        self.padding = 10
        self.calculate_size()
        self.update_position()

    def calculate_size(self):
        max_width = 300  # 최대 너비
        text_width = self.fm.horizontalAdvance(self.text)
        if text_width <= max_width:
            # 한 줄로 표시 가능한 경우
            self.bubble_width = text_width + self.padding * 2
            self.bubble_height = self.fm.height() + self.padding * 2
        else:
            # 여러 줄로 표시해야 하는 경우
            self.bubble_width = max_width
            rect = self.fm.boundingRect(
                QRect(0, 0, max_width, 1000), Qt.TextWordWrap, self.text
            )
            self.bubble_height = rect.height() + self.padding * 2

        self.setFixedSize(self.bubble_width, self.bubble_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 말풍선 그리기
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 200))
        painter.drawRoundedRect(self.rect(), 10, 10)

        # 텍스트 그리기
        painter.setPen(Qt.black)
        painter.setFont(self.font)
        text_rect = self.rect().adjusted(
            self.padding, self.padding, -self.padding, -self.padding
        )
        painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.text)

    def update_position(self):
        parent_rect = self.parent.rect()
        parent_pos = self.parent.mapToGlobal(parent_rect.topLeft())
        x = parent_pos.x() + (parent_rect.width() - self.bubble_width) // 2
        y = parent_pos.y() - self.bubble_height - 10
        self.move(x, y)
