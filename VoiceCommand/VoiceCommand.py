import sys
import os
import random
import webbrowser
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
import keyboard
import time
import logging
from datetime import datetime
import threading
from urllib.parse import quote_plus
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import warnings
import gc

import whisper
import speech_recognition as sr
import torch
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
)
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import (
    QThread,
    Signal,
    QTimer,
    Qt,
)
import warnings
from melo.api import TTS
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QMainWindow,
    QLabel,
    QWidget,
    QPushButton,
    QComboBox,
)
from PySide6.QtGui import QIcon, QPainter, QPixmap, QAction, QImage, QCursor
from PySide6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve, Signal
from pydub import AudioSegment
from pydub.playback import play
from ai_assistant import get_ai_assistant

warnings.filterwarnings("ignore", category=FutureWarning)
os.environ["SDL_VIDEODRIVER"] = "dummy"

# MeCab 경로 지정
mecab_path = r"C:\Program Files\MeCab\bin"
if mecab_path not in os.environ["PATH"]:
    os.environ["PATH"] = mecab_path + os.pathsep + os.environ["PATH"]

# MeCab 사전 경로 지정
dicdir = r"C:\Program Files\MeCab\dic\ipadic"
os.environ["MECAB_DICDIR"] = dicdir

warnings.filterwarnings("ignore", category=DeprecationWarning)
device = "cuda" if torch.cuda.is_available() else "cpu"

# 전역 변수로 TTS 모델 선언
tts_model = None
speaker_ids = None

# 전역 변수로 Whisper 모델 선언
whisper_model = None

# 볼륨 제어를 위한 설정
devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = cast(interface, POINTER(IAudioEndpointVolume))


# 로그 설정
def setup_logging():
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"ari_log_{current_time}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


class ModelLoadingThread(QThread):
    finished = Signal()

    def run(self):
        global tts_model, speaker_ids, whisper_model
        logging.info("TTS 및 Whisper 모델 로딩 중...")
        with torch.no_grad():
            tts_model = TTS(language="KR", device=device)
            speaker_ids = tts_model.hps.data.spk2id
            whisper_model = whisper.load_model("medium", device=device)
        logging.info("TTS 및 Whisper 모델 로딩 완료. " + device)
        self.finished.emit()


def text_to_speech(text):
    global tts_model, speaker_ids
    output_path = os.path.abspath("response.wav")
    tts_model.tts_to_file(text, speaker_ids["KR"], output_path, speed=1.0)

    # TTS 재생 전에 음성 인식을 비활성화
    app = QApplication.instance()
    if app and hasattr(app, "voice_thread") and app.voice_thread:
        app.voice_thread.is_tts_playing = True

    # pydub를 사용하여 오디오 재생
    sound = AudioSegment.from_file(output_path)
    play(sound)
    os.remove(output_path)  # 오디오 파일 삭제

    # TTS 재생 후에 음성 인식을 다시 활성화
    if app and hasattr(app, "voice_thread") and app.voice_thread:
        app.voice_thread.is_tts_playing = False


def shutdown_computer():
    if os.name == "nt":  # Windows
        os.system("shutdown /s /t 1")
    else:  # Linux나 macOS
        os.system("sudo shutdown -h now")


def set_timer(minutes):
    def timer_thread():
        time.sleep(minutes * 60)
        text_to_speech(f"{minutes}분 타이머가 완료되었습니다.")

    threading.Thread(target=timer_thread).start()
    text_to_speech(f"{minutes}분 타이머를 설정했습니다.")


def set_shutdown_timer(minutes):
    def shutdown_timer_thread():
        time.sleep(minutes * 60)
        text_to_speech(f"{minutes}분이 지났습니다. 컴퓨터를 종료합니다.")
        shutdown_computer()

    threading.Thread(target=shutdown_timer_thread).start()
    text_to_speech(f"{minutes}분 후에 컴퓨터를 종료하도록 설정했습니다.")


def open_website(url):
    webbrowser.open(url)
    text_to_speech(f"{url}을(를) 열었습니다.")
    logging.info(f"웹사이트 열기: {url}")


def search_and_play_youtube(query, play=True):
    search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")  # 브라우저를 표시하지 않음
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )

        driver.get(search_url)
        time.sleep(2)  # 페이지 로딩을 위해 잠시 대기

        # 동영상 링크 찾기
        video_link = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a#video-title"))
        )

        first_video_link = video_link.get_attribute("href")
        driver.quit()

        if play == True:
            webbrowser.open(first_video_link)
            text_to_speech(f"{query}에 대한 첫 번째 유튜브 영상을 열었습니다.")
            logging.info(f"유튜브 영상 열기: {first_video_link}")
        else:
            webbrowser.open(search_url)
            text_to_speech(f"{query}에 대한 유튜브 검색 결과를 열었습니다.")
            logging.info(f"유튜브 검색 결과 열기: {search_url}")
    except Exception as e:
        logging.error(f"유튜브 검색 중 오류 발생: {str(e)}")
        text_to_speech("유튜브 검색 중 오류가 발생했습니다.")
        webbrowser.open(search_url)


def execute_command(command):
    logging.info(f"실행할 명령: {command}")

    # 사이트 이름을 매핑하는 사전
    site_mapping = {"네이버": "naver", "유튜브": "youtube"}

    if "열어줘" in command:
        site = command.split("열어줘")[0].strip()

        # 사이트 이름을 매핑된 값으로 변환
        site_key = site_mapping.get(site, site)

        open_website(
            f"https://www.{site_key}.com" if site_key else "https://www.google.com"
        )
        text_to_speech("브라우저를 열었습니다.")
    elif "유튜브" in command and ("재생" in command or "검색" in command):
        query = (
            command.split("유튜브")[1]
            .split("재생" if "재생" in command else "검색")[0]
            .strip()
        )
        search_and_play_youtube(query, play="재생" in command)
    elif "볼륨 키우기" in command or "볼륨 올려" in command:
        adjust_volume(0.1)
        text_to_speech("볼륨을 높였습니다.")
    elif "볼륨 줄이기" in command or "볼륨 내려" in command:
        adjust_volume(-0.1)
        text_to_speech("볼륨을 낮췄습니다.")
    elif "음소거" in command:
        volume.SetMute(1, None)
        text_to_speech("음소거 되었습니다.")
    elif "음소거 해제" in command:
        volume.SetMute(0, None)
        text_to_speech("음소거가 해제되었습니다.")
    elif "타이머" in command:
        set_timer_from_command(command)
    elif "전원 끄기" in command or "컴퓨터 끄기" in command:
        text_to_speech("컴퓨터를 종료합니다.")
        shutdown_computer()
    elif "분 뒤에 전원 꺼줘" in command or "분 후에 전원 꺼줘" in command:
        set_shutdown_timer_from_command(command)
    else:
        text_to_speech("알 수 없는 명령입니다.")


def adjust_volume(change):
    current_volume = volume.GetMasterVolumeLevelScalar()
    new_volume = min(1.0, max(0.0, current_volume + change))
    volume.SetMasterVolumeLevelScalar(new_volume, None)


def set_timer_from_command(command):
    try:
        minutes = int("".join(filter(str.isdigit, command)))
        set_timer(minutes)
    except ValueError:
        text_to_speech("타이머 시간을 정확히 말씀해 주세요.")


def set_shutdown_timer_from_command(command):
    try:
        minutes = int("".join(filter(str.isdigit, command)))
        set_shutdown_timer(minutes)
    except ValueError:
        text_to_speech("종료 시간을 정확히 말씀해 주세요.")


class CharacterWidget(QWidget):
    toggle_voice_recognition = Signal()
    exit_signal = Signal()
    set_listening_state_signal = Signal(bool)

    def __init__(self):
        super().__init__()
        self.is_listening = False
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.initUI()
        self.offset = QPoint()
        self.animation = None
        self.context_menu = None
        self.create_context_menu()
        self.is_moving = False
        self.is_dragging = False
        self.current_frame = 0
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.next_frame)
        self.last_pos = self.pos()

        self.move_timer = QTimer(self)
        self.move_timer.timeout.connect(self.start_random_move)

        self.set_listening_state_signal.connect(self._set_listening_state)
        self.facing_right = False

        self.actions = ["idle", "move", "sit"]
        self.current_action = "idle"
        self.action_timer = QTimer(self)
        self.action_timer.timeout.connect(self.perform_random_action)
        self.action_duration_timer = QTimer(self)
        self.action_duration_timer.timeout.connect(self.end_current_action)

        self.image_cache = {}
        self.load_images()
        self.start_auto_move()

        self.falling = False
        self.fall_timer = QTimer(self)
        self.fall_timer.timeout.connect(self.fall)

        self.fall_frame = 0

        self.interaction_timer = QTimer(self)
        self.interaction_timer.timeout.connect(self.interact_with_others)
        self.interaction_timer.start(5000)  # 5초마다 상호작용 시도

    def initUI(self):
        self.setGeometry(100, 100, 100, 100)

    def load_images(self):
        image_folder = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "images"
        )
        self.idle_image = self.load_and_cache_image(
            os.path.join(image_folder, "idle.png")
        )
        self.move_images = [
            self.load_and_cache_image(os.path.join(image_folder, f"move{i}.png"))
            for i in range(1, 4)
        ]
        self.drag_images = [
            self.load_and_cache_image(os.path.join(image_folder, f"drag{i}.png"))
            for i in range(1, 4)
        ]
        self.listen_image = self.load_and_cache_image(
            os.path.join(image_folder, "listen.png")
        )
        self.sit_image = self.load_and_cache_image(
            os.path.join(image_folder, "sit.png")
        )
        self.fall_images = [
            self.load_and_cache_image(os.path.join(image_folder, f"fall{i}.png"))
            for i in range(1, 4)
        ]
        self.current_image = self.idle_image
        self.resize(QPixmap.fromImage(self.current_image).size())

    def load_and_cache_image(self, path):
        if path not in self.image_cache:
            image = QImage(path)
            scaled_image = image.scaled(
                image.width() * 0.75,
                image.height() * 0.75,
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
        self.frame_timer.stop()

    def start_random_move(self):
        if not self.is_dragging:
            self.animate()

    def animate(self):
        if (
            self.animation is None
            or self.animation.state() == QPropertyAnimation.Stopped
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
            self.current_action = "move"
            self.is_moving = True
            self.frame_timer.start(100)
            self.facing_right = new_x > start_pos.x()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.pos()
            self.is_dragging = True
            self.stop_auto_move()
            self.current_image = self.drag_images[0]
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
            self.current_image = self.idle_image
            self.update()
            self.start_auto_move()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_fall()

    def update_drag_image(self, new_pos):
        if new_pos.x() < self.last_pos.x():
            self.current_image = self.drag_images[2]
            self.facing_right = False
        elif new_pos.x() > self.last_pos.x():
            self.current_image = self.drag_images[1]
            self.facing_right = True
        else:
            self.current_image = self.drag_images[0]
        self.last_pos = new_pos
        self.update()

    def next_frame(self):
        if self.is_moving:
            self.current_frame = (self.current_frame + 1) % len(self.move_images)
            self.current_image = self.move_images[self.current_frame]
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.falling:
            painter.drawPixmap(self.rect(), QPixmap.fromImage(self.current_image))
        elif self.facing_right and not self.is_dragging:
            flipped_image = self.current_image.mirrored(True, False)
            painter.drawPixmap(self.rect(), QPixmap.fromImage(flipped_image))
        else:
            painter.drawPixmap(self.rect(), QPixmap.fromImage(self.current_image))

    def create_context_menu(self):
        self.context_menu = QMenu(self)
        toggle_action = self.context_menu.addAction("음성 인식 토글")
        toggle_action.triggered.connect(self.toggle_voice_recognition.emit)
        sit_action = self.context_menu.addAction("앉기")
        sit_action.triggered.connect(self.sit)
        idle_action = self.context_menu.addAction("기본 상태")
        idle_action.triggered.connect(self.idle)
        fall_action = self.context_menu.addAction("떨어지기")
        fall_action.triggered.connect(self.start_fall)
        exit_action = self.context_menu.addAction("제거")
        exit_action.triggered.connect(self.close)

    def show_context_menu(self, pos):
        self.context_menu.exec_(self.mapToGlobal(pos))

    def closeEvent(self, event):
        self.exit_signal.emit()
        super().closeEvent(event)

    def sit(self):
        self.stop_auto_move()
        self.current_action = "sit"
        self.current_image = self.sit_image
        self.update()

    def idle(self):
        self.current_action = "idle"
        self.current_image = self.idle_image
        self.update()
        self.start_auto_move()

    def animationFinished(self):
        self.is_moving = False
        self.current_image = self.idle_image
        self.frame_timer.stop()
        self.update()

    def set_listening_state(self, is_listening):
        self.set_listening_state_signal.emit(is_listening)

    def _set_listening_state(self, is_listening):
        self.is_listening = is_listening
        if is_listening:
            self.current_image = self.listen_image
            self.stop_auto_move()
            self.action_timer.stop()
            self.action_duration_timer.stop()
        else:
            self.current_image = self.idle_image
            self.start_auto_move()
            self.action_timer.start(random.randint(15000, 45000))
        self.update()

    def perform_random_action(self):
        if not self.is_listening and not self.is_dragging:
            action = random.choice(["idle", "move", "sit"])
            if action == "move":
                self.start_random_move()
            elif action == "sit":
                self.sit()
                duration = random.randint(3000, 8000)
                self.action_duration_timer.start(duration)
            else:
                self.idle()

        self.action_timer.start(random.randint(15000, 45000))

    def end_current_action(self):
        self.action_duration_timer.stop()
        self.idle()

    def start_fall(self):
        if not self.falling:
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
            self.fall_timer.stop()
            new_pos.setY(screen.height() - self.height())
            self.current_image = self.idle_image
            self.start_auto_move()  # 떨어진 후 다시 자동 이동 시작
        else:
            self.fall_frame = (self.fall_frame + 1) % len(self.fall_images)
            self.current_image = self.fall_images[self.fall_frame]

        self.move(new_pos)
        self.update()

    def interact_with_others(self):
        if self.parent() and hasattr(self.parent(), 'character_widgets'):
            others = [char for char in self.parent().character_widgets if char != self]
            if others:
                target = random.choice(others)
                self.move_towards(target.pos())

    def move_towards(self, target_pos):
        if self.falling or self.is_dragging:
            return

        current_pos = self.pos()
        dx = target_pos.x() - current_pos.x()
        dy = target_pos.y() - current_pos.y()
        distance = (dx**2 + dy**2)**0.5
        
        if distance > 5:
            speed = 5
            ratio = speed / distance
            new_x = current_pos.x() + dx * ratio
            new_y = current_pos.y() + dy * ratio
            self.move(QPoint(int(new_x), int(new_y)))
            self.current_image = self.move_images[self.current_frame]
            self.current_frame = (self.current_frame + 1) % len(self.move_images)
            self.update()


class VoiceCommandThread(QThread):
    command_signal = Signal(str)
    finished = Signal()
    start_listening_signal = Signal()
    stop_listening_signal = Signal()

    def __init__(self):
        super().__init__()
        self.recognizer = sr.Recognizer()
        self.is_running = True
        self.is_listening = False
        self.is_processing = False
        self.is_tts_playing = False
        self.falling = False

    def run(self):
        global whisper_model
        while self.is_running:
            if self.is_listening and not self.is_processing and not self.is_tts_playing:
                try:
                    self.is_processing = True
                    with sr.Microphone() as source:
                        logging.info("명령을 기다리는 중...")
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                        audio = self.recognizer.listen(
                            source, timeout=5, phrase_time_limit=5
                        )
                    logging.info("음성 인식 중...")
                    with open("temp_audio.wav", "wb") as f:
                        f.write(audio.get_wav_data())
                    result = whisper_model.transcribe(
                        "temp_audio.wav", language="ko", fp16=False
                    )
                    command = result["text"].strip().lower()
                    logging.info(f"인식된 명령: {command}")
                    if command:
                        self.command_signal.emit(command)
                except sr.WaitTimeoutError:
                    logging.warning("음성 입력 대기 시간 초과")
                except sr.UnknownValueError:
                    logging.warning("음성을 인식할 수 없습니다.")
                except Exception as e:
                    logging.error(f"오류 발생: {str(e)}")
                finally:
                    self.is_processing = False
                    if os.path.exists("temp_audio.wav"):
                        os.remove("temp_audio.wav")
            time.sleep(0.1)

    def stop(self):
        self.is_running = False
        self.wait()  # 스레드가 완전히 종료될 때까지 대기

    def toggle_listening(self):
        if self.is_listening:
            self.stop_listening_signal.emit()
        else:
            self.start_listening_signal.emit()
        self.is_listening = not self.is_listening
        logging.info(f"음성 인식 {'활성화' if self.is_listening else '비활성화'}")


class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self, icon, parent=None):
        super().__init__(icon, parent)
        self.setToolTip("Ari")
        self.create_menu()

        self.loading_thread = ModelLoadingThread()
        self.loading_thread.finished.connect(self.on_model_loaded)
        self.loading_thread.start()

        self.voice_thread = None

        self.last_toggle_time = 0
        self.toggle_cooldown = 1  # 1초

        # keyboard 라이브러리를 사용한 전역 단축키 설정
        keyboard.add_hotkey("ctrl+shift+a", self.toggle_voice_recognition_debounced)

        self.character_widgets = []  # CharacterWidget 인스턴스들을 저장할 리스트
        self.max_characters = 15  # 최대 캐릭터 수
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.start_random_move)
        self.voice_thread = VoiceCommandThread()
        self.voice_thread.command_signal.connect(self.handle_command)
        self.voice_thread.start_listening_signal.connect(self.start_listening)
        self.voice_thread.stop_listening_signal.connect(self.stop_listening)

        self.activated.connect(self.on_tray_icon_activated)

        # 주기적으로 GC를 호출하는 타이머 설정
        self.gc_timer = QTimer(self)
        self.gc_timer.timeout.connect(self.run_gc)
        self.gc_timer.start(30000)  # 30초마다 GC 실행

        try:
            self.ai_assistant = get_ai_assistant()
            print("AI 어시스턴트 초기화 성공")
        except Exception as e:
            print(f"AI 어시스턴트 초기화 실패: {str(e)}")
            self.ai_assistant = None

    def run_gc(self):
        gc.collect()
        logging.info("가비지 컬렉션 실행됨")

    def start_listening(self):
        for character in self.character_widgets:
            character.set_listening_state(True)

    def stop_listening(self):
        for character in self.character_widgets:
            character.set_listening_state(False)

    def create_menu(self):
        menu = QMenu()
        self.toggle_action = QAction("음성 인식 토글 (Ctrl+Shift+A)", self)
        self.toggle_action.setEnabled(False)  # 초기에 비활성화
        menu.addAction(self.toggle_action)

        self.add_character_action = QAction("캐릭터 추가", self)
        self.add_character_action.triggered.connect(self.add_character)
        menu.addAction(self.add_character_action)

        self.remove_character_action = QAction("캐릭터 제거", self)
        self.remove_character_action.triggered.connect(self.remove_character)
        self.remove_character_action.setEnabled(False)  # 초기에 비활성화
        menu.addAction(self.remove_character_action)

        exit_action = menu.addAction("종료")
        self.toggle_action.triggered.connect(self.toggle_voice_recognition)
        exit_action.triggered.connect(self.exit_with_farewell)
        self.setContextMenu(menu)

    def toggle_voice_recognition(self):
        if self.voice_thread:
            self.voice_thread.toggle_listening()
            is_listening = self.voice_thread.is_listening
            for character in self.character_widgets:
                character.set_listening_state(is_listening)
            if is_listening:
                self.animation_timer.stop()
            else:
                self.animation_timer.start(random.randint(3000, 10000))
            self.showMessage(
                "음성 인식",
                f'음성 인식이 {"활성화" if is_listening else "비활성화"}되었습니다.',
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def toggle_voice_recognition_debounced(self):
        current_time = time.time()
        if current_time - self.last_toggle_time > self.toggle_cooldown:
            self.toggle_voice_recognition()
            self.last_toggle_time = current_time

    def on_model_loaded(self):
        self.voice_thread = VoiceCommandThread()
        self.voice_thread.command_signal.connect(self.handle_command)
        self.voice_thread.finished.connect(self.exit_with_farewell)
        self.voice_thread.start()
        self.toggle_action.setEnabled(True)
        self.showMessage(
            "Ari",
            "TTS 및 음성 인식 준비 완료",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def handle_command(self, command):
        logging.info(f"받은 명령: {command}")
        if "종료" in command:
            logging.info("프로그램을 종료합니다.")
            self.toggle_action.setEnabled(False)  # 토글 버튼 비활성화
            self.exit_with_farewell()
        elif "아리" in command or "아리야" in command or "아리아" in command:
            # "아리" 이후의 명령만 추출
            _, *command_parts = command.split(
                "아리야"
                if "아리야" in command
                else "아리아" if "아리아" in command else "아리"
            )
            if command_parts:
                actual_command = command_parts[-1].strip()
                logging.info(f"실제 실행할 명령: {actual_command}")
                if any(
                    keyword in actual_command
                    for keyword in [
                        "열어줘",
                        "볼륨",
                        "타이머",
                        "전원 끄기",
                        "컴퓨터 끄기",
                        "유튜브"
                    ]
                ):
                    execute_command(actual_command)
                else:
                    # AI 모델을 사용하여 응답 생성
                    if self.ai_assistant is not None:
                        try:
                            response = self.ai_assistant.process_query(actual_command)
                            if response:
                                logging.info(f"AI 응답: {response}")
                                # TTS를 사용하여 응답을 음성으로 출력
                                text_to_speech(response)
                            else:
                                logging.error("AI 응답이 비어 있습니다.")
                                text_to_speech("죄송합니다. 응답을 생성하는 데 문제가 있었습니다.")
                        except Exception as e:
                            logging.error(f"AI 응답 처리 중 오류 발생: {str(e)}")
                            text_to_speech("죄송합니다. 응답을 처리하는 데 문제가 발생했습니다.")
                    else:
                        logging.error("AI 어시스턴트가 초기화되지 않았습니다.")
                        text_to_speech("죄송합니다. AI 어시스턴트를 사용할 수 없습니다.")
            else:
                logging.info("추가 명령이 없습니다.")
                text_to_speech("네, 무엇을 도와드릴까요?")
        else:
            logging.info("'아리'로 시작하는 명령이 아닙니다.")
        # 명령어 실행 후
        for character in self.character_widgets:
            character.set_listening_state(False)
        self.voice_thread.is_listening = False
        self.animation_timer.start(
            random.randint(3000, 10000)
        )  # 명령 처리 후 애니메이션 타이머 재시작

    def exit_with_farewell(self):
        farewells = ["안녕히 가세요.", "아리를 종료합니다."]
        farewell = random.choice(farewells)
        text_to_speech(farewell)
        logging.info("프로그램을 종료합니다.")
        for character in self.character_widgets:
            character.close()
        self.character_widgets.clear()
        QTimer.singleShot(2000, self.exit)  # 2초 후에 exit 메서드 호출

    def exit(self):
        keyboard.unhook_all()  # 모든 단축키 해제
        if self.voice_thread:
            self.voice_thread.stop()
            self.voice_thread.wait()  # 스레드가 완전히 종료될 때까지 대기
        QApplication.instance().quit()  # 애플리케이션 종료

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            parent = self.parent()
            if isinstance(parent, QMainWindow):
                parent.show()
                parent.raise_()
                parent.activateWindow()

    def add_character(self):
        if len(self.character_widgets) < self.max_characters:
            character = CharacterWidget(self.parent())  # parent 설정
            character.show()
            character.exit_signal.connect(lambda: self.remove_specific_character(character))
            self.character_widgets.append(character)
            self.remove_character_action.setEnabled(True)
            if len(self.character_widgets) == self.max_characters:
                self.add_character_action.setEnabled(False)
        else:
            self.showMessage("Ari", f"최대 캐릭터 수({self.max_characters}마리)에 도달했습니다.", QSystemTrayIcon.Information, 2000)

    def remove_character(self):
        if self.character_widgets:
            character = self.character_widgets.pop()
            character.close()
            if not self.character_widgets:
                self.remove_character_action.setEnabled(False)
            self.add_character_action.setEnabled(True)
        else:
            self.showMessage(
                "Ari",
                "제거할 캐릭터가 없습니다.",
                QSystemTrayIcon.Information,
                2000,
            )

    def remove_specific_character(self, character):
        if character in self.character_widgets:
            self.character_widgets.remove(character)
            character.close()
            if not self.character_widgets:
                self.remove_character_action.setEnabled(False)
            self.add_character_action.setEnabled(True)
            if hasattr(self.parent(), "update_character_count"):
                self.parent().update_character_count()

    def start_random_move(self):
        for character in self.character_widgets:
            character.start_random_move()

class CharacterWidget(QWidget):
    exit_signal = Signal()
    toggle_voice_recognition = Signal()
    set_listening_state_signal = Signal(bool)

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

        self.facing_right = False
        self.actions = ["idle", "move", "sit"]
        self.current_action = "idle"

        self.image_cache = {}
        self.falling = False
        self.fall_frame = 0

        self.initUI()
        self.load_images()
        self.start_auto_move()

    def initUI(self):
        self.setGeometry(100, 100, 100, 100)

        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.next_frame)

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
        toggle_action = self.context_menu.addAction("음성 인식 토글")
        toggle_action.triggered.connect(self.toggle_voice_recognition.emit)
        sit_action = self.context_menu.addAction("앉기")
        sit_action.triggered.connect(self.sit)
        idle_action = self.context_menu.addAction("기본 상태")
        idle_action.triggered.connect(self.idle)
        fall_action = self.context_menu.addAction("떨어지기")
        fall_action.triggered.connect(self.start_fall)
        exit_action = self.context_menu.addAction("제거")
        exit_action.triggered.connect(self.close)

    def load_images(self):
        image_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
        self.idle_image = self.load_and_cache_image(os.path.join(image_folder, "idle.png"))
        self.move_images = [self.load_and_cache_image(os.path.join(image_folder, f"move{i}.png")) for i in range(1, 4)]
        self.drag_images = [self.load_and_cache_image(os.path.join(image_folder, f"drag{i}.png")) for i in range(1, 4)]
        self.listen_image = self.load_and_cache_image(os.path.join(image_folder, "listen.png"))
        self.sit_image = self.load_and_cache_image(os.path.join(image_folder, "sit.png"))
        self.fall_images = [self.load_and_cache_image(os.path.join(image_folder, f"fall{i}.png")) for i in range(1, 4)]
        self.current_image = self.idle_image
        self.resize(QPixmap.fromImage(self.current_image).size())

    def load_and_cache_image(self, path):
        if path not in self.image_cache:
            image = QImage(path)
            scaled_image = image.scaled(
                image.width() * 0.75,
                image.height() * 0.75,
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
        self.frame_timer.stop()

    def start_random_move(self):
        if not self.is_dragging:
            self.animate()

    def animate(self):
        if self.animation is None or self.animation.state() == QPropertyAnimation.Stopped:
            self.animation = QPropertyAnimation(self, b"pos")
            self.animation.setDuration(3000)
            start_pos = self.pos()
            self.animation.setStartValue(start_pos)

            screen = QApplication.primaryScreen().geometry()
            max_distance = 100
            new_x = max(0, min(start_pos.x() + random.randint(-max_distance, max_distance), screen.width() - self.width()))
            new_y = max(0, min(start_pos.y() + random.randint(-max_distance, max_distance), screen.height() - self.height()))

            self.animation.setEndValue(QPoint(new_x, new_y))
            self.animation.setEasingCurve(QEasingCurve.InOutQuad)
            self.animation.finished.connect(self.animationFinished)
            self.animation.start()
            self.current_action = "move"
            self.is_moving = True
            self.frame_timer.start(100)
            self.facing_right = new_x > start_pos.x()

    def animationFinished(self):
        self.is_moving = False
        self.current_image = self.idle_image
        self.frame_timer.stop()
        self.update()

    def next_frame(self):
        if self.is_moving:
            self.current_frame = (self.current_frame + 1) % len(self.move_images)
            self.current_image = self.move_images[self.current_frame]
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.falling:
            painter.drawPixmap(self.rect(), QPixmap.fromImage(self.current_image))
        elif self.facing_right and not self.is_dragging:
            flipped_image = self.current_image.mirrored(True, False)
            painter.drawPixmap(self.rect(), QPixmap.fromImage(flipped_image))
        else:
            painter.drawPixmap(self.rect(), QPixmap.fromImage(self.current_image))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.pos()
            self.is_dragging = True
            self.stop_auto_move()
            self.current_image = self.drag_images[0]
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
            self.current_image = self.idle_image
            self.update()
            self.start_auto_move()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_fall()

    def update_drag_image(self, new_pos):
        if new_pos.x() < self.last_pos.x():
            self.current_image = self.drag_images[2]
            self.facing_right = False
        elif new_pos.x() > self.last_pos.x():
            self.current_image = self.drag_images[1]
            self.facing_right = True
        else:
            self.current_image = self.drag_images[0]
        self.last_pos = new_pos
        self.update()

    def show_context_menu(self, pos):
        self.context_menu.exec_(self.mapToGlobal(pos))

    def closeEvent(self, event):
        self.exit_signal.emit()
        super().closeEvent(event)

    def sit(self):
        self.stop_auto_move()
        self.current_action = "sit"
        self.current_image = self.sit_image
        self.update()

    def idle(self):
        self.current_action = "idle"
        self.current_image = self.idle_image
        self.update()
        self.start_auto_move()

    def _set_listening_state(self, is_listening):
        self.is_listening = is_listening
        if is_listening:
            self.current_image = self.listen_image
            self.stop_auto_move()
            self.action_timer.stop()
            self.action_duration_timer.stop()
        else:
            self.current_image = self.idle_image
            self.start_auto_move()
            self.action_timer.start(random.randint(15000, 45000))
        self.update()

    def perform_random_action(self):
        if not self.is_listening and not self.is_dragging:
            action = random.choice(["idle", "move", "sit"])
            if action == "move":
                self.start_random_move()
            elif action == "sit":
                self.sit()
                duration = random.randint(3000, 8000)
                self.action_duration_timer.start(duration)
            else:
                self.idle()

        self.action_timer.start(random.randint(15000, 45000))

    def end_current_action(self):
        self.action_duration_timer.stop()
        self.idle()

    def start_fall(self):
        if not self.falling:
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
            self.fall_timer.stop()
            new_pos.setY(screen.height() - self.height())
            self.current_image = self.idle_image
            self.start_auto_move()
        else:
            self.fall_frame = (self.fall_frame + 1) % len(self.fall_images)
            self.current_image = self.fall_images[self.fall_frame]

        self.move(new_pos)
        self.update()

    def interact_with_others(self):
        if self.parent() and hasattr(self.parent(), 'character_widgets'):
            others = [char for char in self.parent().character_widgets if char != self]
            if others:
                target = random.choice(others)
                self.move_towards(target.pos())

    def move_towards(self, target_pos):
        if self.falling or self.is_dragging:
            return

        current_pos = self.pos()
        dx = target_pos.x() - current_pos.x()
        dy = target_pos.y() - current_pos.y()
        distance = (dx**2 + dy**2)**0.5
        
        if distance > 5:
            speed = 5
            ratio = speed / distance
            new_x = current_pos.x() + dx * ratio
            new_y = current_pos.y() + dy * ratio
            self.move(QPoint(int(new_x), int(new_y)))
            self.current_image = self.move_images[self.current_frame]
            self.current_frame = (self.current_frame + 1) % len(self.move_images)
            self.update()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ari Voice Command - 마이크 설정")
        self.setGeometry(100, 100, 300, 250)  # 윈도우 크기 조정
        self.setFixedSize(300, 200)  # 윈도우 크기를 고정

        self.tray_icon = SystemTrayIcon(QIcon(icon_path), self)
        self.tray_icon.show()

        # 여기에 캐릭터를 추가하는 코드를 넣습니다.
        self.tray_icon.add_character()

        self.initUI()

    def initUI(self):
        # 마이크 설정 UI 추가
        self.microphone_label = QLabel("마이크 선택:", self)
        self.microphone_label.setGeometry(20, 50, 80, 30)

        self.microphone_combo = QComboBox(self)
        self.microphone_combo.setGeometry(100, 50, 180, 30)
        self.microphone_combo.addItems(sr.Microphone.list_microphone_names())

        self.save_button = QPushButton("저장", self)
        self.save_button.setGeometry(100, 100, 100, 30)
        self.save_button.clicked.connect(self.save_settings)

    def save_settings(self):
        selected_microphone = self.microphone_combo.currentText()
        logging.info(f"선택된 마이크: {selected_microphone}")
        # 마이크 설정 저장 로직 추가
        self.hide()  # 설정을 저장한 후 창을 닫음
        self.tray_icon.showMessage(
            "Ari",
            "마이크 설정이 저장되었습니다.",
            QSystemTrayIcon.Information,
            2000,
        )

    def closeEvent(self, event):
        self.tray_icon.exit_with_farewell()
        event.ignore()


def main():
    try:
        setup_logging()
        logging.info("프로그램 시작")
        app = QApplication(sys.argv)

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logging.error("시스템 트레이를 사용할 수 없습니다.")
            sys.exit(1)

        app.setQuitOnLastWindowClosed(False)

        global icon_path
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        if not os.path.exists(icon_path):
            logging.warning("아이콘 파일이 없습니다. 기본 아이콘을 사용합니다.")
            icon_path = None

        main_window = MainWindow()
        main_window.show()  # 메인 윈도우를 표시합니다.

        tray_icon = main_window.tray_icon

        app.voice_thread = tray_icon.voice_thread

        app.aboutToQuit.connect(tray_icon.exit)

        sys.exit(app.exec())
    except Exception as e:
        logging.error(f"예외 발생: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"예외 발생: {str(e)}")
        sys.exit(1)
