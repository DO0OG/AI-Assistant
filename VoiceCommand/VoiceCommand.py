import sys
import os
import setproctitle
import random
import webbrowser
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
import json
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
import warnings
import gc
import psutil
import whisper
import speech_recognition as sr
import torch
import pvporcupine
import pyaudio
import struct
import ctypes
import threading
from queue import Queue
import time
import requests
from datetime import datetime, timedelta
import math
from geopy.geocoders import Nominatim
from datetime import datetime, timedelta
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
from PySide6.QtGui import QIcon, QAction, QPainter, QPixmap, QImage, QFont, QFontDatabase, QColor, QFontMetrics
from PySide6.QtCore import (
    QThread,
    Signal,
    QTimer,
    Qt,
    QPoint,
    QPropertyAnimation,
    QEasingCurve,
    QMetaObject,
    Qt,
    Q_ARG,
    QRect,
    Slot,
    QBuffer
)
from melo.api import TTS
from pydub import AudioSegment
from pydub.playback import play
from ai_assistant import get_ai_assistant
from collections import OrderedDict


# 전역 변수 선언
tts_model = None
speaker_ids = None
whisper_model = None
ai_assistant = None
icon_path = None
volume = None
active_timer = None

try:
    ctypes.windll.kernel32.SetConsoleTitleW("Ari Voice Command")
except:
    pass

warnings.filterwarnings("ignore", category=FutureWarning)
os.environ["SDL_VIDEODRIVER"] = "dummy"

# MeCab 경로 지정
mecab_path = r"C:\Program Files\MeCab\bin"
if mecab_path not in os.environ["PATH"]:
    os.environ["PATH"] = mecab_path + os.pathsep + os.environ["PATH"]

# MeCab 사전 경로 지정
dicdir = r"C:\Program Files\MeCab\dic\ipadic"
os.environ["MECAB_DICDIR"] = dicdir

icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
if not os.path.exists(icon_path):
    print(f"경고: 아이콘 파일을 찾을 수 없습니다: {icon_path}")
    icon_path = None  # 아이콘 파일이 없을 경우 None으로


# 설정 파일에서 API 키 로드
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


config = load_config()

warnings.filterwarnings("ignore", category=DeprecationWarning)
device = "cuda" if torch.cuda.is_available() else "cpu"


# 볼륨 제어를 위한 설정
devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = cast(interface, POINTER(IAudioEndpointVolume))


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
    cache.put(path, scaled_image)
    return scaled_image


# 로그 설정
def setup_logging():
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"ari_log_{current_time}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),  # stdout으로 변경
        ],
    )


# 리소스 모니터링 스레드
class ResourceMonitor(QThread):
    gc_needed = Signal()

    def __init__(
        self, memory_threshold=20, cpu_threshold=30, check_interval=5
    ):
        super().__init__()
        self.memory_threshold = memory_threshold
        self.cpu_threshold = cpu_threshold
        self.check_interval = check_interval

    def run(self):
        while self.running:
            memory_percent = psutil.virtual_memory().percent
            cpu_percent = psutil.cpu_percent(interval=1)

            if (
                memory_percent > self.memory_threshold
                or cpu_percent > self.cpu_threshold
            ):
                self.gc_needed.emit()

            time.sleep(self.check_interval)

    def stop(self):
        self.running = False


# 가비지 컬렉션 실행
def perform_gc():
    logging.info("가비지 컬렉션 실행 중...")
    gc.collect()
    logging.info("가비지 컬렉션 완료")


# 모델 로딩 스레드
class ModelLoadingThread(QThread):
    finished = Signal()
    progress = Signal(str)

    def run(self):
        global tts_model, speaker_ids, whisper_model
        try:
            self.progress.emit("TTS 모델 로딩 중...")
            with torch.no_grad():
                tts_model = TTS(language="KR", device=device)
                speaker_ids = tts_model.hps.data.spk2id

            self.progress.emit("Whisper 모델 로딩 중...")
            whisper_model = whisper.load_model("medium", device=device)

            logging.info("TTS 및 Whisper 모델 로딩 완료. " + device)
        except Exception as e:
            logging.error(f"모델 로딩 중 오류 발생: {str(e)}")
        finally:
            self.finished.emit()


def text_to_speech(text):
    global tts_model, speaker_ids, tts_thread
    if tts_model is None or speaker_ids is None:
        logging.error("TTS 모델이 초기화되지 않았습니다.")
        return

    try:
        output_path = os.path.abspath("response.wav")
        tts_model.tts_to_file(text, speaker_ids["KR"], output_path, speed=1.0)

        # TTS 재생 전에 음성 인식을 비활성화
        app = QApplication.instance()
        main_window = next((w for w in app.topLevelWidgets() if isinstance(w, MainWindow)), None)
        if main_window and hasattr(main_window, "voice_thread") and main_window.voice_thread:
            main_window.voice_thread.is_tts_playing = True

        # 말풍선 표시
        if main_window and hasattr(main_window, "tray_icon"):
            for character in main_window.tray_icon.character_widgets:
                QMetaObject.invokeMethod(character, "show_speech_bubble", 
                                         Qt.QueuedConnection, 
                                         Q_ARG(str, text))

        # pydub를 사용하여 오디오 재생
        sound = AudioSegment.from_file(output_path)
        play(sound)
        os.remove(output_path)  # 오디오 파일 삭제

        # TTS 재생 후에 음성 인식을 다시 활성화
        if main_window and hasattr(main_window, "voice_thread") and main_window.voice_thread:
            main_window.voice_thread.is_tts_playing = False

        # 말풍선 숨기기
        if main_window and hasattr(main_window, "tray_icon"):
            for character in main_window.tray_icon.character_widgets:
                character.hide_speech_bubble()
                
    except Exception as e:
        logging.error(f"TTS 처리 중 오류 발생: {str(e)}")


def shutdown_computer():
    if os.name == "nt":  # Windows
        os.system("shutdown /s /t 1")
    else:  # Linux나 macOS
        os.system("sudo shutdown -h now")


def cancel_timer():
    global active_timer
    if active_timer:
        active_timer.cancel()
        active_timer = None
        text_to_speech("타이머가 취소되었습니다.")
    else:
        text_to_speech("현재 실행 중인 타이머가 없습니다.")


def set_timer(minutes):
    global active_timer

    def timer_thread():
        global active_timer
        time.sleep(minutes * 60)
        if active_timer:  # 타이머가 취소되지 않았다면
            text_to_speech(f"{minutes}분 타이머가 완료되었습니다.")
            active_timer = None

    if active_timer:
        active_timer.cancel()
    active_timer = threading.Timer(minutes * 60, timer_thread)
    active_timer.start()
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


def get_current_time():
    now = datetime.now()
    return now.strftime("%H시 %M분")


def get_current_location():
    try:
        # 외부 IP를 기반으로 위치 정보 가져오기
        ip_response = requests.get("https://ipapi.co/json/")
        ip_data = ip_response.json()
        latitude = ip_data.get("latitude", 37.5665)  # 기본값은 서울의 위도
        longitude = ip_data.get("longitude", 126.9780)  # 기본값은 서울의 경도

        logging.info(f"IP 기반 위치: 위도 {latitude}, 경도 {longitude}")

        # 한국 내 위치인지 확인
        if 33 <= latitude <= 38 and 124 <= longitude <= 132:
            return latitude, longitude
        else:
            logging.warning("현재 위치가 한국 밖입니다. 서울의 좌표를 사용합니다.")
            return 37.5665, 126.9780  # 서울의 위도, 경도
    except Exception as e:
        logging.error(f"위치 정보 가져오기 실패: {str(e)}")
        return 37.5665, 126.9780  # 오류 발생 시 서울의 좌표 반환


def get_weather_info(lat, lon):
    base_url = (
        "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
    )
    service_key = config["weather_api_key"]

    now = datetime.now()
    base_date = now.strftime("%Y%m%d")
    base_time = (now - timedelta(hours=1)).strftime("%H00")

    nx, ny = convert_coord(lat, lon)

    params = {
        "serviceKey": service_key,
        "pageNo": "1",
        "numOfRows": "1000",
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": str(nx),
        "ny": str(ny),
    }

    logging.info(f"API 요청 파라미터: {params}")

    try:
        response = requests.get(base_url, params=params, verify=False)
        response.raise_for_status()

        logging.info(f"API 응답: {response.text}")

        data = response.json()

        if data['response']['header']['resultCode'] == '00':
            items = data['response']['body']['items']['item']
            
            weather_info = {}
            for item in items:
                category = item['category']
                value = item['obsrValue']
                weather_info[category] = value
            
            temp = float(weather_info.get('T1H', 'N/A'))
            humidity = int(weather_info.get('REH', 'N/A'))
            rain = float(weather_info.get('RN1', '0'))
            
            weather_status = "맑음"
            if rain > 0:
                weather_status = "비"
            elif int(weather_info.get('PTY', '0')) > 0:
                weather_status = "눈 또는 비"
            
            # 소수점을 "점"으로 바꾸고, 숫자를 읽기 쉽게 조정
            temp_str = f"{int(temp)}점 {int((temp % 1) * 10)}"
            rain_str = f"{int(rain)}점 {int((rain % 1) * 10)}"

            return (f"현재 날씨는 {weather_status}입니다. "
                    f"기온은 {temp_str}도, 습도는 {humidity}퍼센트, "
                    f"강수량은 {rain_str}밀리미터입니다.")
        else:
            logging.error(f"API 오류: {data['response']['header']['resultMsg']}")
            return "날씨 정보를 가져오는 데 실패했습니다."
    except requests.exceptions.RequestException as e:
        logging.error(f"요청 오류: {str(e)}")
        return "날씨 정보를 가져오는 데 실패했습니다."
    except ValueError as e:
        logging.error(f"JSON 파싱 오류: {str(e)}")
        return "날씨 정보를 가져오는 데 실패했습니다."


def convert_coord(lat, lon):
    # 위경도를 기상청 격자 좌표로 변환하는 함수
    RE = 6371.00877  # 지구 반경(km)
    GRID = 5.0  # 격자 간격(km)
    SLAT1 = 30.0  # 투영 위도1(degree)
    SLAT2 = 60.0  # 투영 위도2(degree)
    OLON = 126.0  # 기준점 경도(degree)
    OLAT = 38.0  # 기준점 위도(degree)
    XO = 43  # 기준점 X좌표(GRID)
    YO = 136  # 기준점 Y좌표(GRID)

    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / math.pow(ro, sn)

    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / math.pow(ra, sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    x = math.floor(ra * math.sin(theta) + XO + 0.5)
    y = math.floor(ro - ra * math.cos(theta) + YO + 0.5)

    return int(x), int(y)


def execute_command(command):
    logging.info(f"실행할 명령: {command}")

    # 사이트 이름을 매핑하는 사전
    site_mapping = {"네이버": "naver", "유튜브": "youtube"}

    if "열어 줘" in command:
        site = command.split("열어 줘")[0].strip()

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
    elif "검색해 줘" in command:
        site = command.split("검색해 줘")[0].strip()
        open_website(f"https://www.google.com/search?q={site}")
        text_to_speech(f"{site}에 대한 검색 결과입니다.")
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
        if "취소" in command or "끄기" in command or "중지" in command:
            cancel_timer()
        else:
            set_timer_from_command(command)
    elif "몇 시야" in command:
        current_time = get_current_time()
        response = f"현재 시간은 {current_time}입니다."
        text_to_speech(response)
        logging.info(f"현재 시간 안내: {response}")
    elif "전원 꺼 줘" in command or "컴퓨터 꺼 줘" in command:
        text_to_speech("컴퓨터를 종료합니다.")
        shutdown_computer()
    elif "분 뒤에 컴퓨터 꺼 줘" in command or "분 후에 컴퓨터 꺼 줘" in command:
        set_shutdown_timer_from_command(command)
    elif "날씨 어때" in command:
        try:
            lat, lon = get_current_location()
            logging.info(f"현재 위치: 위도 {lat}, 경도 {lon}")
            weather_info = get_weather_info(lat, lon)
            text_to_speech(weather_info)
        except Exception as e:
            logging.error(f"날씨 정보 조회 중 오류 발생: {str(e)}")
            text_to_speech("날씨 정보를 가져오는 데 실패했습니다.")
    else:
        response = ai_assistant.process_query(command)
        text_to_speech(response)


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

    def __init__(self, parent=None):
        super().__init__(parent)
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

        self.image_cache = LRUCache(20)
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
        self.image_cache = LRUCache(50)  # 캐시 크기 제한
        self.image_sets = {
            "idle": [
                load_and_cache_image(
                    os.path.join(image_folder, f"idle{i}.png"), self.image_cache
                )
                for i in range(1, 9)
            ],
            "walk": [
                load_and_cache_image(
                    os.path.join(image_folder, f"walk{i}.png"), self.image_cache
                )
                for i in range(1, 10)
            ],
            "sit": [
                load_and_cache_image(
                    os.path.join(image_folder, f"sit{i}.png"), self.image_cache
                )
                for i in range(1, 10)
            ],
        }
        self.current_image = self.image_sets["idle"][0]
        self.resize(QPixmap.fromImage(self.current_image).size())

    def load_and_cache_image(self, path):
        cached_image = self.image_cache.get(path)
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

        self.image_cache.put(path, compressed_image)
        return compressed_image

    def get_image_set(self, action):
        if action not in self.image_sets:
            image_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
            if action == 'drag':
                self.image_sets[action] = [self.load_and_cache_image(os.path.join(image_folder, f"drag{i}.png")) for i in range(1, 9)]
            elif action == 'fall':
                self.image_sets[action] = [self.load_and_cache_image(os.path.join(image_folder, f"fall{i}.png")) for i in range(1, 9)]
        return self.image_sets[action]

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
        if self.parent() and hasattr(self.parent(), "character_widgets"):
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
        distance = (dx**2 + dy**2) ** 0.5

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
        super(SystemTrayIcon, self).__init__(icon, parent)
        self.setToolTip(f"Ari Voice Command")

        self.menu = QMenu(parent)
        self.setContextMenu(self.menu)

        self.character_widgets = []
        self.max_characters = 5

        self.activated.connect(self.on_tray_icon_activated)

        self.add_character_action = self.menu.addAction("캐릭터 추가")
        self.add_character_action.triggered.connect(self.add_character)

        self.remove_character_action = self.menu.addAction("캐릭터 제거")
        self.remove_character_action.triggered.connect(self.remove_character)
        self.remove_character_action.setEnabled(False)

        self.exit_action = self.menu.addAction("종료")
        self.exit_action.triggered.connect(self.exit)

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.start_random_move)
        self.animation_timer.start(random.randint(3000, 10000))

        self.voice_thread = None  # voice_thread 속성 추가

    def set_voice_thread(self, thread):
        self.voice_thread = thread

    def exit(self):
        if self.voice_thread:
            self.voice_thread.stop()
            self.voice_thread.wait()
        for character in self.character_widgets:
            character.close()
        self.character_widgets.clear()
        QApplication.instance().quit()

    def on_model_loaded(self):
        # 이 메서드는 더 이상 필요하지 않지만, 오류를 방지하기 위해 빈 메서드로 유지합니다.
        pass

    def create_menu(self):
        menu = QMenu()
        self.add_character_action = QAction("캐릭터 추가", self)
        self.add_character_action.triggered.connect(self.add_character)
        menu.addAction(self.add_character_action)

        self.remove_character_action = QAction("캐릭터 제거", self)
        self.remove_character_action.triggered.connect(self.remove_character)
        self.remove_character_action.setEnabled(False)
        menu.addAction(self.remove_character_action)

        exit_action = menu.addAction("종료")
        exit_action.triggered.connect(self.exit_with_farewell)
        self.setContextMenu(menu)

    def handle_command(self, command):
        logging.info(f"받은 명령: {command}")
        if "종료" in command:
            logging.info("프로그램을 종료합니다.")
            self.exit_with_farewell()
        else:
            if self.ai_assistant is not None:
                try:
                    response = self.ai_assistant.process_query(command)
                    if response:
                        logging.info(f"AI 응답: {response}")
                        text_to_speech(response)
                    else:
                        logging.error("AI 응답이 비어 있습니다.")
                        text_to_speech(
                            "죄송합니다. 응답을 생성하는 데 문제가 있었습니다."
                        )
                except Exception as e:
                    logging.error(f"AI 응답 처리 중 오류 발생: {str(e)}")
                    text_to_speech(
                        "죄송합니다. 응답을 처리하는 데 문제가 발생했습니다."
                    )
            else:
                logging.error("AI 어시스턴트가 초기화되지 않았습니다.")
                text_to_speech("죄송합니다. AI 어시스턴트를 사용할 수 없습니다.")
        for character in self.character_widgets:
            character.set_listening_state(False)
        self.animation_timer.start(random.randint(3000, 10000))

    def exit_with_farewell(self):
        farewells = ["안녕히 가세요.", "아리를 종료합니다."]
        farewell = random.choice(farewells)
        text_to_speech(farewell)
        logging.info("프로그램을 종료합니다.")
        for character in self.character_widgets:
            character.close()
        self.character_widgets.clear()
        QTimer.singleShot(2000, self.exit)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.parent().show()
            self.parent().activateWindow()

    def add_character(self):
        if len(self.character_widgets) < self.max_characters:
            character = CharacterWidget(self.parent())
            character.show()
            character.exit_signal.connect(
                lambda: self.remove_specific_character(character)
            )
            self.character_widgets.append(character)
            self.remove_character_action.setEnabled(True)
            if len(self.character_widgets) == self.max_characters:
                self.add_character_action.setEnabled(False)
        else:
            self.showMessage(
                "Ari",
                f"최대 캐릭터 수({self.max_characters}마리)에 도달했습니다.",
                QSystemTrayIcon.Information,
                2000,
            )

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

class VoiceRecognitionThread(QThread):
    result = Signal(str)
    listening_state_changed = Signal(bool)

    def __init__(self, selected_microphone=None):
        super().__init__()
        self.running = True
        self.porcupine = None
        self.pa = None
        self.audio_stream = None
        self.selected_microphone = selected_microphone
        self.microphone_index = None
        self.access_key = config["picovoice_access_key"]  # Picovoice 콘솔에서 받은 액세스 키
        # 현재 스크립트 파일의 디렉토리 경로를 가져옵니다
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # 키워드 파일 경로를 현재 디렉토리 기준으로 설정합니다
        self.keyword_path = os.path.join(current_dir, "아리야아_ko_windows_v3_0_0.ppn")
        self.model_path = os.path.join(current_dir, "porcupine_params_ko.pv")

        # 키워드 파일이 존재하는지 확인합니다
        if not os.path.exists(self.keyword_path):
            logging.error(f"키워드 파일을 찾을 수 없습니다: {self.keyword_path}")
            raise FileNotFoundError(
                f"키워드 파일을 찾을 수 없습니다: {self.keyword_path}"
            )

    def run(self):
        try:
            self.init_porcupine()
            self.init_audio()
            
            while self.running:
                pcm = self.audio_stream.read(self.porcupine.frame_length)
                pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm)

                keyword_index = self.porcupine.process(pcm)
                if keyword_index >= 0:
                    self.handle_wake_word()

        except Exception as e:
            logging.error(f"오류 발생: {str(e)}", exc_info=True)
        finally:
            self.cleanup()

    def init_porcupine(self):
        logging.info("Porcupine 초기화 중...")
        self.porcupine = pvporcupine.create(
            access_key=self.access_key,
            keyword_paths=[self.keyword_path],
            model_path=self.model_path,
            sensitivities=[0.5],
        )
        logging.info("Porcupine 초기화 완료")

    def init_audio(self):
        logging.info("PyAudio 초기화 중...")
        self.pa = pyaudio.PyAudio()
        logging.info("PyAudio 초기화 완료")

        self.init_microphone()

        logging.info("오디오 스트림 열기...")
        self.audio_stream = self.pa.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=self.microphone_index,
            frames_per_buffer=self.porcupine.frame_length,
        )
        logging.info("오디오 스트림 열기 완료")

    def handle_wake_word(self):
        logging.info("웨이크 워드 '아리야' 감지!")
        wake_responses = ["네?", "부르셨나요?"]
        response = random.choice(wake_responses)
        text_to_speech(response)
        self.listening_state_changed.emit(True)
        self.recognize_speech()
        self.listening_state_changed.emit(False)

    def cleanup(self):
        logging.info("음성 인식 스레드 종료 중...")
        if self.audio_stream is not None:
            self.audio_stream.close()
        if self.pa is not None:
            self.pa.terminate()
        if self.porcupine is not None:
            self.porcupine.delete()
        logging.info("음성 인식 스레드 종료 완료")

    def init_microphone(self):
        if self.selected_microphone:
            self.microphone_index = self.get_device_index(self.selected_microphone)
        else:
            # 기본 마이크 사용
            self.microphone_index = None
        logging.info(f"선택된 마이크 인덱스: {self.microphone_index}")

    def get_device_index(self, device_name):
        for index, name in enumerate(sr.Microphone.list_microphone_names()):
            if device_name in name:
                return index
        logging.warning(
            f"지정된 마이크를 찾을 수 없습니다: {device_name}. 기본 마이크를 사용합니다."
        )
        return None

    def recognize_speech(self):
        r = sr.Recognizer()
        try:
            with sr.Microphone(device_index=self.microphone_index) as source:
                logging.info("말씀해 주세요...")
                audio = r.listen(source, timeout=5, phrase_time_limit=5)

            text = r.recognize_google(audio, language="ko-KR")
            logging.info(f"인식된 텍스트: {text}")
            self.result.emit(text)
        except sr.UnknownValueError:
            logging.warning("음성을 인식할 수 없습니다.")
        except sr.RequestError as e:
            logging.error(f"음성 인식 서비스 오류: {e}")
        except Exception as e:
            logging.error(f"음성 인식 중 오류 발생: {str(e)}", exc_info=True)

    def stop(self):
        self.running = False

    def set_microphone(self, microphone_name):
        self.selected_microphone = microphone_name
        self.init_microphone()


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
            logging.warning("DNFBitBitv2.ttf 폰트를 로드할 수 없습니다. 기본 폰트를 사용합니다.")
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
        idle_action.triggered.connect(self.return_to_idle)  # idle() 대신 return_to_idle() 사용
        fall_action = self.context_menu.addAction("떨어지기")
        fall_action.triggered.connect(self.start_fall)
        exit_action = self.context_menu.addAction("제거")
        exit_action.triggered.connect(self.close)

    def load_images(self):
        image_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
        self.image_sets = {
            'idle': [self.load_and_cache_image(os.path.join(image_folder, f"idle{i}.png")) for i in range(1, 9)],
            'walk': [self.load_and_cache_image(os.path.join(image_folder, f"walk{i}.png")) for i in range(1, 10)],
            'drag': [self.load_and_cache_image(os.path.join(image_folder, f"drag{i}.png")) for i in range(1, 9)],
            'listen': [self.load_and_cache_image(os.path.join(image_folder, f"sit{i}.png")) for i in range(1, 10)],
            'sit': [self.load_and_cache_image(os.path.join(image_folder, f"sit{i}.png")) for i in range(1, 10)],
            'fall': [self.load_and_cache_image(os.path.join(image_folder, f"fall{i}.png")) for i in range(1, 9)]
        }
        self.current_image = self.image_sets['idle'][0]
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
        if not self.is_dragging and not self.is_listening and self.current_action != "sit" and not self.falling:
            self.animate()

    def animate(self):
        if (self.animation is None or self.animation.state() == QPropertyAnimation.Stopped) and not self.is_listening and self.current_action != "sit" and not self.falling:
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
        action = 'fall' if self.falling else (
            'drag' if self.is_dragging else (
            'walk' if self.is_moving and not self.is_listening else (
            'sit' if self.current_action == "sit" or self.is_listening else 'idle'
        )))
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
            self.current_image = self.image_sets['drag'][0]
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
        self.current_image = self.image_sets['sit'][0]
        self.update()
        self.action_timer.stop()  # 앉아있는 동안 자동 행동 타이머 중지

    def idle(self):
        self.return_to_idle()
        self.start_auto_move()

    def return_to_idle(self):
        self.current_action = "idle"
        self.current_image = self.image_sets['idle'][0]
        self.update()
        self.action_timer.start(random.randint(15000, 45000))  # 자동 행동 타이머 재시작

    def _set_listening_state(self, is_listening):
        self.is_listening = is_listening
        if is_listening:
            self.current_action = "sit"
            self.current_image = self.image_sets['sit'][0]
            self.stop_auto_move()
            self.action_timer.stop()
            self.action_duration_timer.stop()
        else:
            self.current_action = "idle"
            self.current_image = self.image_sets['idle'][0]
            self.start_auto_move()
            self.action_timer.start(random.randint(15000, 45000))
        self.update()

    def set_listening_state(self, is_listening):
        self.set_listening_state_signal.emit(is_listening)

    def perform_random_action(self):
        if not self.is_listening and not self.is_dragging and self.current_action != "sit" and not self.falling:
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
        if self.falling or self.is_dragging or self.is_listening or self.current_action == "sit":
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

    @Slot()
    def hide_speech_bubble(self):
        if self.speech_bubble:
            self.speech_bubble.hide()
            self.speech_bubble = None
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


# TTS 스레드
class TTSThread(QThread):
    def __init__(self):
        super().__init__()
        self.queue = Queue()

    def run(self):
        while True:
            text = self.queue.get()
            if text is None:
                break
            text_to_speech(text)
            self.queue.task_done()

    def speak(self, text):
        self.queue.put(text)


# 명령 실행 스레드
class CommandExecutionThread(QThread):
    def __init__(self):
        super().__init__()
        self.queue = Queue()

    def run(self):
        while True:
            command = self.queue.get()
            if command is None:
                break
            execute_command(command)
            self.queue.task_done()

    def execute(self, command):
        self.queue.put(command)


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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ari Voice Command")
        self.setGeometry(100, 100, 300, 250)
        self.setFixedSize(300, 200)

        global icon_path
        if icon_path:
            self.tray_icon = SystemTrayIcon(QIcon(icon_path), self)
        else:
            self.tray_icon = SystemTrayIcon(QIcon(), self)  # 빈 아이콘으로 생성
        self.tray_icon.show()

        self.tray_icon.add_character()

        self.initUI()

        self.model_loading_thread = ModelLoadingThread()
        self.model_loading_thread.finished.connect(self.on_model_loaded)
        self.model_loading_thread.start()
        self.tray_icon.showMessage(
            "Ari", "TTS 및 Whisper 모델 로딩 중...", QSystemTrayIcon.Information, 3000
        )

        self.resource_monitor = ResourceMonitor()
        self.resource_monitor.gc_needed.connect(perform_gc)
        self.resource_monitor.start()

        self.voice_thread = VoiceRecognitionThread()
        self.tts_thread = TTSThread()
        self.command_thread = CommandExecutionThread()

        self.voice_thread.result.connect(self.handle_voice_result)
        self.voice_thread.listening_state_changed.connect(
            self.update_listening_state
        )

        self.voice_thread.start()
        self.tts_thread.start()
        self.command_thread.start()

    def initUI(self):
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
        try:
            if hasattr(self, "voice_thread") and self.voice_thread:
                self.voice_thread.selected_microphone = selected_microphone
                self.voice_thread.init_microphone()
            self.hide()
            self.tray_icon.showMessage(
                "Ari",
                "마이크 설정이 저장되었습니다.",
                QSystemTrayIcon.Information,
                2000,
            )
        except Exception as e:
            logging.error(f"마이크 설정 저장 중 오류 발생: {str(e)}")
            self.tray_icon.showMessage(
                "Ari",
                "마이크 설정 저장 중 오류가 발생했습니다.",
                QSystemTrayIcon.Warning,
                2000,
            )

    def closeEvent(self, event):
        self.resource_monitor.stop()
        self.resource_monitor.wait()
        self.voice_thread.stop()
        self.tts_thread.queue.put(None)
        self.command_thread.queue.put(None)
        self.voice_thread.wait()
        self.tts_thread.wait()
        self.command_thread.wait()
        event.ignore()
        self.hide()

    def on_model_loaded(self):
        logging.info("모델 로딩이 완료되었습니다.")
        # 로딩 완료 알림
        self.tray_icon.showMessage(
            "Ari", "TTS 및 Whisper 모델 로딩 완료!", QSystemTrayIcon.Information, 3000
        )
        # 여기에 모델 로딩 완료 후 수행할 추가 작업을 넣을 수 있습니다.

    def show_loading_progress(self, message):
        self.tray_icon.showMessage("Ari", message, QSystemTrayIcon.Information, 2000)

    # 윈도우를 보여주는 메서드 추가
    def show_window(self):
        self.show()
        self.activateWindow()

    def handle_voice_result(self, text):
        logging.info(f"인식된 명령: {text}")
        self.command_thread.execute(text)

    def update_listening_state(self, is_listening):
        for character in self.tray_icon.character_widgets:
            character.set_listening_state(is_listening)


def main():
    global ai_assistant, icon_path, tts_thread
    setproctitle.setproctitle("Ari Voice Command")
    try:
        setup_logging()
        logging.info("프로그램 시작")

        app = QApplication(sys.argv)
        main_window = MainWindow()
        main_window.show()

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logging.error("시스템 트레이를 사용할 수 없습니다.")
            sys.exit(1)

        app.setQuitOnLastWindowClosed(False)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        if not os.path.exists(icon_path):
            logging.warning("아이콘 파일이 없습니다. 기본 아이콘을 사용합니다.")
            icon_path = None

        tray_icon = main_window.tray_icon
        tts_thread = main_window.tts_thread

        # AI 어시스턴트 초기화
        try:
            ai_assistant = get_ai_assistant()
        except Exception as e:
            logging.error(f"AI 어시스턴트 초기화 실패: {str(e)}")
            sys.exit(1)

        # 마이크 설정 변경 시 음성 인식 스레드에 알림
        def update_microphone():
            selected_microphone = main_window.microphone_combo.currentText()
            main_window.voice_thread.set_microphone(selected_microphone)

        main_window.save_button.clicked.connect(update_microphone)

        # 종료 시 정리
        app.aboutToQuit.connect(main_window.voice_thread.stop)
        app.aboutToQuit.connect(main_window.voice_thread.wait)
        app.aboutToQuit.connect(lambda: main_window.tts_thread.queue.put(None))
        app.aboutToQuit.connect(lambda: main_window.command_thread.queue.put(None))
        app.aboutToQuit.connect(main_window.tts_thread.wait)
        app.aboutToQuit.connect(main_window.command_thread.wait)
        app.aboutToQuit.connect(main_window.tray_icon.exit)
        app.aboutToQuit.connect(main_window.resource_monitor.stop)
        app.aboutToQuit.connect(main_window.resource_monitor.wait)

        sys.exit(app.exec())
    except Exception as e:
        logging.error(f"예외 발생: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
