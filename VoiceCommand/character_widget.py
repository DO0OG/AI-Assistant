"""
Shimeji 스타일 캐릭터 위젯 (최적화 버전)
"""
import os
import random
from collections import OrderedDict
from PySide6.QtWidgets import QWidget, QLabel
from PySide6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QImage, QPainter


class LRUCache:
    """LRU 캐시 구현"""
    def __init__(self, capacity=20):
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
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)


class CharacterWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.dragging = False
        self.offset = QPoint()
        self.current_animation = "idle"
        self.frame_index = 0
        self.animations = {}
        self.image_cache = LRUCache(capacity=20)
        self.facing_right = True  # 캐릭터 방향

        # 윈도우 설정
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 애니메이션 로드
        self.load_animations()

        # 레이블 생성
        self.label = QLabel(self)
        self.update_frame()

        # 애니메이션 타이머 (10 FPS)
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.next_frame)
        self.animation_timer.start(100)

        # 행동 타이머 (3~10초마다)
        self.behavior_timer = QTimer(self)
        self.behavior_timer.timeout.connect(self.random_behavior)
        self.start_behavior_timer()

        # 이동 애니메이션
        self.move_animation = None

        # 화면 하단으로 이동
        self.move_to_bottom()
        self.show()

    def load_and_cache_image(self, path, flip=False):
        """이미지 로드 및 캐싱 (압축 포함)"""
        cache_key = f"{path}_{'flip' if flip else 'normal'}"
        cached = self.image_cache.get(cache_key)
        if cached:
            return cached

        if not os.path.exists(path):
            return None

        # 이미지 로드 및 1.5배 스케일
        image = QImage(path)

        # 좌우 반전
        if flip:
            image = image.mirrored(horizontal=True, vertical=False)

        scaled_image = image.scaled(
            int(image.width() * 1.5),
            int(image.height() * 1.5),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        # QPixmap으로 변환 (렌더링 최적화)
        pixmap = QPixmap.fromImage(scaled_image)
        self.image_cache.put(cache_key, pixmap)
        return pixmap

    def load_animations(self):
        """애니메이션 프레임 로드"""
        animations = {
            "idle": 8,
            "walk": 9,
            "drag": 8,
            "fall": 8,
            "sit": 9
        }

        images_dir = os.path.join(os.path.dirname(__file__), "images")

        for anim_name, frame_count in animations.items():
            frames = []
            for i in range(1, frame_count + 1):
                img_path = os.path.join(images_dir, f"{anim_name}{i}.png")
                pixmap = self.load_and_cache_image(img_path)
                if pixmap:
                    frames.append(img_path)  # 경로만 저장 (메모리 절약)

            if frames:
                self.animations[anim_name] = frames

    def update_frame(self):
        """현재 프레임 업데이트"""
        if self.current_animation in self.animations:
            frames = self.animations[self.current_animation]
            if frames:
                frame_path = frames[self.frame_index % len(frames)]
                # 왼쪽을 향할 때 이미지 반전
                flip = not self.facing_right
                pixmap = self.load_and_cache_image(frame_path, flip=flip)
                if pixmap:
                    self.label.setPixmap(pixmap)
                    self.label.adjustSize()
                    self.setFixedSize(self.label.size())

    def next_frame(self):
        """다음 프레임으로"""
        if self.current_animation in self.animations:
            frame_count = len(self.animations[self.current_animation])
            self.frame_index = (self.frame_index + 1) % frame_count
            self.update_frame()

    def set_animation(self, animation_name):
        """애니메이션 변경"""
        if animation_name in self.animations and animation_name != self.current_animation:
            self.current_animation = animation_name
            self.frame_index = 0
            self.update_frame()

    def start_behavior_timer(self):
        """랜덤 간격으로 행동 타이머 시작"""
        interval = random.randint(3000, 10000)  # 3~10초
        self.behavior_timer.start(interval)

    def random_behavior(self):
        """랜덤 행동"""
        if self.dragging or (self.move_animation and self.move_animation.state() == QPropertyAnimation.Running):
            return

        # 행동 선택
        behaviors = ["idle", "sit"]
        if random.random() < 0.4:  # 40% 확률로 걷기
            behaviors.append("walk")

        behavior = random.choice(behaviors)
        self.set_animation(behavior)

        # 걷기 애니메이션이면 이동
        if behavior == "walk":
            self.smooth_walk()

        # 다음 행동 타이머 재설정
        self.start_behavior_timer()

    def smooth_walk(self):
        """부드러운 걷기 이동"""
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()

        # 이동 거리 및 방향
        distance = random.randint(100, 300)
        direction = random.choice([-1, 1])
        new_x = self.x() + (distance * direction)

        # 화면 경계 체크
        new_x = max(0, min(new_x, screen.width() - self.width()))

        # 캐릭터 방향 설정 (오른쪽 이동 = facing_right True)
        self.facing_right = (new_x > self.x())
        self.update_frame()  # 방향 변경 즉시 반영

        # QPropertyAnimation으로 부드러운 이동
        if self.move_animation:
            self.move_animation.stop()

        self.move_animation = QPropertyAnimation(self, b"pos")
        self.move_animation.setDuration(3000)  # 3초
        self.move_animation.setStartValue(self.pos())
        self.move_animation.setEndValue(QPoint(new_x, self.y()))
        self.move_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.move_animation.finished.connect(lambda: self.set_animation("idle"))
        self.move_animation.start()

    def move_to_bottom(self):
        """화면 하단으로 이동"""
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = random.randint(0, max(0, screen.width() - 100))
        y = screen.height() - 150  # 하단에서 150px 위
        self.move(x, y)

    def mousePressEvent(self, event):
        """마우스 클릭"""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.offset = event.pos()
            self.set_animation("drag")

            # 이동 애니메이션 중지
            if self.move_animation:
                self.move_animation.stop()

            # 드래그 중 애니메이션 타이머 느리게
            self.animation_timer.setInterval(150)

    def mouseMoveEvent(self, event):
        """마우스 드래그 (최적화)"""
        if self.dragging:
            new_pos = self.mapToParent(event.pos() - self.offset)
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        """마우스 릴리즈"""
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.animation_timer.setInterval(100)  # 원래 속도로 복원
            self.set_animation("fall")
            # 0.8초 후 idle로 전환
            QTimer.singleShot(800, lambda: self.set_animation("idle") if not self.dragging else None)

    def cleanup(self):
        """정리"""
        if self.animation_timer:
            self.animation_timer.stop()
        if self.behavior_timer:
            self.behavior_timer.stop()
        if self.move_animation:
            self.move_animation.stop()
        self.image_cache.cache.clear()
        self.close()
