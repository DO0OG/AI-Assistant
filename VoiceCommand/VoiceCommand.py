import os
import random
import webbrowser
import time
import logging
from urllib.parse import quote_plus
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
import warnings
import speech_recognition as sr
import torch
import pyaudio
import sounddevice as sd
import numpy as np
import threading
from datetime import datetime, timedelta
from queue import Queue
import requests
import math
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, Signal
from melo.api import TTS
from pydub import AudioSegment
from pydub.playback import play
from Config import use_api
import pvporcupine
from vosk import Model, KaldiRecognizer
import json

# 전역 변수 선언
tts_model = None
speaker_ids = None
ai_assistant = None
icon_path = None
pulse = None
active_timer = None
active_shutdown_timer = None


def set_ai_assistant(assistant):
    global ai_assistant
    ai_assistant = assistant


warnings.filterwarnings("ignore", category=DeprecationWarning)
device = "cuda" if torch.cuda.is_available() else "cpu"


# 모델 로딩 스레드
class ModelLoadingThread(QThread):
    finished = Signal()
    progress = Signal(str)

    def run(self):
        global tts_model, speaker_ids
        try:
            self.progress.emit("TTS 모델 로딩 중...")
            with torch.no_grad():
                tts_model = TTS(language="KR", device=device)
                speaker_ids = tts_model.hps.data.spk2id

            logging.info("TTS 모델 로딩 완료. " + device)
        except Exception as e:
            logging.error(f"모델 로딩 중 오류 발생: {str(e)}")
        finally:
            self.finished.emit()


class VoskRecognizer:
    def __init__(self, model_path):
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, 16000)
        self.mic = pyaudio.PyAudio()
        self.stream = self.mic.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=8192,
        )
        self.stream.start_stream()

    def listen(self):
        while True:
            data = self.stream.read(4096)
            if len(data) == 0:
                break
            if self.recognizer.AcceptWaveform(data):
                result = self.recognizer.Result()
                return result

    def close(self):
        self.stream.stop_stream()
        self.stream.close()
        self.mic.terminate()


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
        main_window = next(
            (w for w in app.topLevelWidgets() if w.objectName() == "MainWindow"), None
        )
        if (
            main_window
            and hasattr(main_window, "voice_thread")
            and main_window.voice_thread
        ):
            main_window.voice_thread.is_tts_playing = True

        # 말풍선 표시
        if main_window:
            main_window.show_speech_bubble(text)

        # pydub를 사용하여 오디오 재생
        sound = AudioSegment.from_file(output_path)
        play(sound)
        os.remove(output_path)  # 오디오 파일 삭제

        # TTS 재생 후에 음성 인식을 다시 활성화
        if (
            main_window
            and hasattr(main_window, "voice_thread")
            and main_window.voice_thread
        ):
            main_window.voice_thread.is_tts_playing = False

        # 말풍선 숨기기
        if main_window:
            main_window.hide_speech_bubble()

    except Exception as e:
        logging.error(f"TTS 처리 중 오류 발생: {str(e)}")


def shutdown_computer():
    os.system("sudo shutdown -h now")


def cancel_timer():
    global active_timer, active_shutdown_timer
    if active_timer:
        active_timer["timer"].cancel()
        active_timer = None
        text_to_speech("타이머가 취소되었습니다.")
    if active_shutdown_timer:
        active_shutdown_timer["timer"].cancel()
        active_shutdown_timer = None
        text_to_speech("컴퓨터 종료 타이머가 취소되었습니다.")
    if not active_timer and not active_shutdown_timer:
        text_to_speech("현재 실행 중인 타이머가 없습니다.")


def set_timer(minutes):
    global active_timer

    def timer_thread():
        global active_timer
        if active_timer and datetime.now() >= active_timer["end_time"]:
            text_to_speech(f"{minutes}분 타이머가 완료되었습니다.")
            active_timer = None
        elif active_timer:
            # 1초마다 확인하도록 새로운 타이머 설정
            threading.Timer(1, timer_thread).start()

    if active_timer:
        active_timer["timer"].cancel()

    end_time = datetime.now() + timedelta(minutes=minutes)
    active_timer = {"timer": threading.Timer(1, timer_thread), "end_time": end_time}
    active_timer["timer"].start()
    text_to_speech(f"{minutes}분 타이머를 설정했습니다.")


def set_shutdown_timer(minutes):
    global active_shutdown_timer

    def shutdown_timer_thread():
        global active_shutdown_timer
        if (
            active_shutdown_timer
            and datetime.now() >= active_shutdown_timer["end_time"]
        ):
            text_to_speech(f"{minutes}분이 지났습니다. 컴퓨터를 종료합니다.")
            shutdown_computer()
            active_shutdown_timer = None
        elif active_shutdown_timer:
            # 1초마다 확인하도록 새로운 타이머 설정
            threading.Timer(1, shutdown_timer_thread).start()

    if active_shutdown_timer:
        active_shutdown_timer["timer"].cancel()

    end_time = datetime.now() + timedelta(minutes=minutes)
    active_shutdown_timer = {
        "timer": threading.Timer(1, shutdown_timer_thread),
        "end_time": end_time,
    }
    active_shutdown_timer["timer"].start()
    text_to_speech(f"{minutes}분 후에 컴퓨터를 종료하도록 설정했습니다.")


def open_website(url):
    webbrowser.open(url)
    logging.info(f"웹사이트 열기: {url}")


def search_and_play_youtube(query, play=True):
    search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    try:
        options = Options()
        options.add_argument("--headless")
        driver = webdriver.Firefox(
            service=Service(GeckoDriverManager().install()), options=options
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
    service_key = use_api("weather_api_key")

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

        if data["response"]["header"]["resultCode"] == "00":
            items = data["response"]["body"]["items"]["item"]

            weather_info = {}
            for item in items:
                category = item["category"]
                value = item["obsrValue"]
                weather_info[category] = value

            temp = float(weather_info.get("T1H", "N/A"))
            humidity = int(weather_info.get("REH", "N/A"))
            rain = float(weather_info.get("RN1", "0"))

            weather_status = "맑음"
            if rain > 0:
                weather_status = "비"
            elif int(weather_info.get("PTY", "0")) > 0:
                weather_status = "눈 또는 비"

            # 소수점을 "점"으로 바꾸고, 숫자를 읽기 쉽게 조정
            temp_str = f"{int(temp)}점 {int((temp % 1) * 10)}"
            rain_str = f"{int(rain)}점 {int((rain % 1) * 10)}"

            return (
                f"현재 날씨는 {weather_status}입니다. "
                f"기온은 {temp_str}도, 습도는 {humidity}퍼센트, "
                f"강수량은 {rain_str}밀리미터입니다."
            )
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
    global learning_mode
    logging.info(f"실행할 명령: {command}")

    if "학습 모드" in command:
        if "비활성화" in command or "종료" in command:
            learning_mode = False
            text_to_speech("학습 모드가 비활성화되었습니다.")
        elif "활성화" in command or "시작" in command:
            learning_mode = True
            text_to_speech("학습 모드가 활성화되었습니다.")
        return

    # 사이트 이름을 매핑하는 사전
    site_mapping = {"네이버": "naver", "유튜브": "youtube", "구글": "google"}

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
    elif "음소거 해제" in command:
        adjust_volume(0)  # 음소거 해제를 위해 현재 볼륨을 유지
        text_to_speech("음소거가 해제되었습니다.")
    elif "음소거" in command:
        adjust_volume(-1)  # 음소거를 위해 볼륨을 0으로 설정
        text_to_speech("음소거 되었습니다.")
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
    elif "분 뒤에 컴퓨터 꺼 줘" in command or "분 후에 컴퓨터 꺼 줘" in command:
        set_shutdown_timer_from_command(command)
    elif "전원 꺼 줘" in command or "컴퓨터 꺼 줘" in command:
        text_to_speech("컴퓨터를 종료합니다.")
        shutdown_computer()
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
        response, entities, sentiment = ai_assistant.process_query(command)
        text_to_speech(response)
        logging.info(f"인식된 개체: {entities}")
        logging.info(f"감성 분석 결과: {sentiment}")

        if learning_mode:
            text_to_speech("응답이 적절했나요? '적절' 또는 '부적절'로 대답해주세요.")
            feedback = listen_for_feedback()

            if "부적절" in feedback.lower():
                text_to_speech("새로운 응답을 말씀해 주세요.")
                new_response = listen_for_new_response()
                if new_response:
                    ai_assistant.learn_new_response(command, new_response)
                    text_to_speech("새로운 응답을 학습했습니다. 감사합니다.")

                    # 강화학습 업데이트
                    ai_assistant.update_q_table(command, "say_sorry", -1, command)
                else:
                    text_to_speech("새로운 응답을 학습하지 못했습니다. 죄송합니다.")
            else:
                text_to_speech(
                    "감사합니다. 앞으로도 좋은 답변을 드리도록 노력하겠습니다."
                )

                # 강화학습 업데이트
                ai_assistant.update_q_table(command, "use_best_response", 1, command)


def listen_for_feedback():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        logging.info("피드백 대기 중...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=3)

    try:
        feedback = recognizer.recognize_google(audio, language="ko-KR")
        logging.info(f"인식된 피드백: {feedback}")
        return feedback
    except sr.UnknownValueError:
        logging.warning("피드백을 인식하지 못했습니다.")
        return "인식 실패"
    except sr.RequestError as e:
        logging.error(f"음성 인식 서비스 오류: {e}")
        return "오류 발생"


def listen_for_new_response():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        logging.info("새로운 응답 대기 중...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source, timeout=10, phrase_time_limit=10)

    try:
        new_response = recognizer.recognize_google(audio, language="ko-KR")
        logging.info(f"인식된 새로운 응답: {new_response}")
        return new_response
    except sr.UnknownValueError:
        text_to_speech("죄송합니다. 응답을 이해하지 못했습니다. 다시 말씀해 주세요.")
        return listen_for_new_response()
    except sr.RequestError as e:
        logging.error(f"음성 인식 서비스 오류: {e}")
        text_to_speech(
            "음성 인식 서비스에 문제가 발생했습니다. 나중에 다시 시도해 주세요."
        )
        return None


def get_voice_feedback():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("피드백을 말씀해주세요...")
        audio = r.listen(source, timeout=5, phrase_time_limit=3)

    try:
        feedback = r.recognize_google(audio, language="ko-KR")
        return feedback.lower()
    except sr.UnknownValueError:
        print("음성을 인식할 수 없습니다.")
        return None
    except sr.RequestError as e:
        print(f"음성 인식 서비스 오류: {e}")
        return None


def get_current_time():
    now = datetime.now()
    if now.hour < 12:
        am_pm = "오전"
        hour = now.hour
    else:
        am_pm = "오후"
        hour = now.hour - 12 if now.hour > 12 else 12
    return f"{am_pm} {hour}시 {now.minute}분"


def adjust_volume(change):
    try:
        import alsaaudio

        mixer = alsaaudio.Mixer()
        current_volume = mixer.getvolume()[0]
        new_volume = max(0, min(100, current_volume + int(change * 100)))
        mixer.setvolume(new_volume)
        logging.info(f"볼륨이 {new_volume}로 조정되었습니다.")
    except Exception as e:
        logging.error(f"볼륨 조절 실패: {str(e)}")


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


class VoiceCommandThread(QThread):
    command_signal = Signal(str)
    finished = Signal()
    start_listening_signal = Signal()
    stop_listening_signal = Signal()

    def __init__(self):
        super().__init__()
        self.recognizer = sr.Recognizer()
        self.vosk_recognizer = VoskRecognizer(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "vosk-model-small-ko-0.22"
            )
        )
        self.is_running = True
        self.is_listening = False
        self.is_processing = False
        self.is_tts_playing = False

    def run(self):
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

                    # Vosk를 사용한 음성 인식
                    raw_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
                    vosk_result = self.vosk_recognizer.process_audio(raw_data)
                    if vosk_result:
                        command = vosk_result
                        logging.info(f"Vosk로 인식된 명령: {command}")
                        self.command_signal.emit(command)
                    else:
                        # Vosk로 인식되지 않은 경우, Google Speech Recognition 사용
                        command = self.recognizer.recognize_google(
                            audio, language="ko-KR"
                        )
                        logging.info(f"Google로 인식된 명령: {command}")
                        self.command_signal.emit(command)

                except sr.WaitTimeoutError:
                    logging.warning("음성 입력 대기 시간 초과")
                except sr.UnknownValueError:
                    logging.warning("음성을 인식할 수 없습니다.")
                except Exception as e:
                    logging.error(f"오류 발생: {str(e)}")
                finally:
                    self.is_processing = False
            time.sleep(0.1)

    def stop(self):
        self.is_running = False
        self.wait()

    def toggle_listening(self):
        if self.is_listening:
            self.stop_listening_signal.emit()
        else:
            self.start_listening_signal.emit()
        self.is_listening = not self.is_listening
        logging.info(f"음성 인식 {'활성화' if self.is_listening else '비활성화'}")


class VoiceRecognitionThread(QThread):
    result = Signal(str)
    listening_state_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.running = True
        self.porcupine = None
        self.audio_stream = None
        self.access_key = use_api("picovoice_access_key")
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.keyword_path = os.path.join(
            current_dir, "아리야아_ko_raspberry-pi_v3_0_0.ppn"
        )
        self.model_path = os.path.join(current_dir, "porcupine_params_ko.pv")
        self.vosk_model = Model(os.path.join(current_dir, "vosk-model-ko-0.22"))
        self.recognizer = KaldiRecognizer(self.vosk_model, 16000)
        self.is_listening = False
        self.is_processing = False
        self.is_tts_playing = False

        # Vosk 모델 초기화 추가
        self.vosk_model_path = os.path.join(current_dir, "vosk-model-ko-0.22")
        self.vosk_recognizer = VoskRecognizer(self.vosk_model_path)

    def run(self):
        try:
            self.init_porcupine()
            self.init_audio()

            while self.running:
                pcm = self.audio_stream.read(
                    self.porcupine.frame_length, exception_on_overflow=False
                )
                pcm = np.frombuffer(pcm, dtype=np.int16)

                keyword_index = self.porcupine.process(pcm)
                if keyword_index >= 0:
                    self.handle_wake_word()

                # Vosk를 사용한 음성 인식 추가
                if (
                    self.is_listening
                    and not self.is_processing
                    and not self.is_tts_playing
                ):
                    try:
                        self.is_processing = True
                        pcm = self.audio_stream.read(
                            self.porcupine.frame_length, exception_on_overflow=False
                        )
                        pcm = np.frombuffer(pcm, dtype=np.int16)

                        # Vosk로 음성 인식
                        if self.recognizer.AcceptWaveform(pcm.tobytes()):
                            result = self.recognizer.Result()
                            vosk_result = json.loads(result)["text"]
                            if vosk_result:
                                logging.info(f"Vosk 인식 결과: {vosk_result}")
                                self.result.emit(vosk_result)
                    except Exception as e:
                        logging.error(f"Vosk 음성 인식 중 오류 발생: {str(e)}")
                    finally:
                        self.is_processing = False

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
        logging.info("오디오 초기화 중...")
        p = pyaudio.PyAudio()

        # ALSA 장치 찾기
        alsa_device_index = None
        for i in range(p.get_device_count()):
            dev_info = p.get_device_info_by_index(i)
            if "sysdefault" in dev_info["name"].lower():
                alsa_device_index = i
                break

        if alsa_device_index is None:
            logging.warning(
                "ALSA 기본 장치를 찾을 수 없습니다. 시스템 기본 장치를 사용합니다."
            )
            alsa_device_index = p.get_default_input_device_info()["index"]

        logging.info(f"선택된 ALSA 장치 인덱스: {alsa_device_index}")

        self.audio_stream = p.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.porcupine.frame_length,
            input_device_index=alsa_device_index,
        )
        logging.info("오디오 초기화 완료")

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
        if hasattr(self, "audio_stream") and self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        if self.porcupine is not None:
            self.porcupine.delete()
        logging.info("음성 인식 스레드 종료 완료")

    def recognize_speech(self):
        r = sr.Recognizer()
        try:
            with sr.Microphone(device_index=self.microphone_index) as source:
                logging.info("말씀해 주세요...")
                audio = r.listen(source, timeout=5, phrase_time_limit=5)

            text = r.recognize_google(audio, language="ko-KR")
            logging.info(f"인식된 텍스트: {text}")
            self.result.emit(text)

            # AI 어시스턴트 응답 처리
            response = ai_assistant.process_query(text)
            text_to_speech(response)

            # 응답의 적절성 확인
            text_to_speech("응답이 적절했나요? 예 또는 아니오로 대답해주세요.")
            feedback = get_voice_feedback()

            if feedback == "예":
                ai_assistant.learn_from_interaction(True)
            elif feedback == "아니오":
                ai_assistant.learn_from_interaction(False)
            else:
                text_to_speech("죄송합니다. 응답을 이해하지 못했습니다.")

        except sr.UnknownValueError:
            logging.warning("음성을 인식할 수 없습니다.")
        except sr.RequestError as e:
            logging.error(f"음성 인식 서비스 오류: {e}")
        except Exception as e:
            logging.error(f"음성 인식 중 오류 발생: {str(e)}", exc_info=True)

    def stop(self):
        self.running = False
        self.wait()  # 스레드가 완전히 종료될 때까지 대기


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
