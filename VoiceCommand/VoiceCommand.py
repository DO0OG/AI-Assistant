import os
import time
import logging
import warnings
import random
import speech_recognition as sr
from datetime import datetime
from queue import Queue
from PySide6.QtCore import QThread, Signal
from pydub import AudioSegment
from pydub.playback import play
from Config import use_api
import json
from fish_tts import FishTTS
from rp_generator import RPGenerator
from simple_wake import SimpleWakeWord

# 새로운 모듈 import
from weather_service import WeatherService
from timer_manager import TimerManager

# 전역 변수 선언
ai_assistant = None
learning_mode = False
fish_tts = None
rp_gen = None


def initialize_tts():
    """Fish TTS 초기화"""
    global fish_tts, rp_gen
    try:
        import json
        with open("ari_settings.json", "r", encoding="utf-8") as f:
            settings = json.load(f)

        fish_tts = FishTTS(
            api_key=settings.get("fish_api_key", ""),
            reference_id=settings.get("fish_reference_id", "")
        )

        rp_gen = RPGenerator()
        rp_gen.set_config(
            personality=settings.get("personality", ""),
            scenario=settings.get("scenario", ""),
            system_prompt=settings.get("system_prompt", ""),
            history_instruction=settings.get("history_instruction", "")
        )

        logging.info("Fish TTS 및 RP 초기화 완료")
    except Exception as e:
        logging.warning(f"설정 로드 실패: {e}")
        fish_tts = FishTTS()
        rp_gen = RPGenerator()


# 초기화
initialize_tts()

# 모듈 인스턴스 초기화
weather_service = None
timer_manager = None


def initialize_modules():
    """기능 모듈 초기화"""
    global weather_service, timer_manager

    def tts_callback(text):
        tts_wrapper(text)

    weather_service = WeatherService(api_key="")
    timer_manager = TimerManager(tts_callback=tts_callback)

    logging.info("기능 모듈 초기화 완료")


# 모듈 초기화
initialize_modules()


def set_ai_assistant(assistant):
    global ai_assistant
    ai_assistant = assistant


warnings.filterwarnings("ignore", category=DeprecationWarning)


def text_to_speech(text):
    """Fish TTS로 음성 출력"""
    global fish_tts, rp_gen

    try:
        # RP 텍스트 생성
        if rp_gen:
            text = rp_gen.generate(text)

        # TTS 재생
        if fish_tts:
            success = fish_tts.speak(text)
            if not success:
                logging.error("TTS 재생 실패")
        else:
            logging.error("Fish TTS 미초기화")
    except Exception as e:
        logging.error(f"TTS 오류: {e}")


def tts_wrapper(text):
    text_to_speech(text)


def execute_command(command):
    """명령 실행 (새 모듈 사용)"""
    global learning_mode
    logging.info(f"실행할 명령: {command}")

    # 학습 모드 제어
    if "학습 모드" in command:
        if "비활성화" in command or "종료" in command:
            learning_mode = False
            tts_wrapper("학습 모드가 비활성화되었습니다.")
        elif "활성화" in command or "시작" in command:
            learning_mode = True
            tts_wrapper("학습 모드가 활성화되었습니다.")
        return

    # 타이머 명령
    elif "타이머" in command:
        if "취소" in command or "끄기" in command or "중지" in command:
            timer_manager.cancel()
        else:
            minutes = timer_manager.parse_timer_command(command)
            if minutes:
                timer_manager.set_timer(minutes)
            else:
                tts_wrapper("타이머 시간을 정확히 말씀해 주세요.")

    # 날씨 명령
    elif "날씨 어때" in command:
        try:
            weather_info = weather_service.get_weather()
            tts_wrapper(weather_info)
        except Exception as e:
            logging.error(f"날씨 정보 조회 중 오류 발생: {str(e)}")
            tts_wrapper("날씨 정보를 가져오는 데 실패했습니다.")

    # 시스템 명령
    elif "볼륨" in command:
        if "키우기" in command or "올려" in command:
            adjust_volume(0.1)
        elif "줄이기" in command or "내려" in command:
            adjust_volume(-0.1)
        elif "음소거 해제" in command:
            adjust_volume(0)
        elif "음소거" in command:
            adjust_volume(-1)
    elif "몇 시야" in command:
        time_str = get_current_time()
        response = f"현재 시간은 {time_str}입니다."
        tts_wrapper(response)
        logging.info(f"현재 시간 안내: {response}")

    # AI 어시스턴트 (기본)
    else:
        response, entities, sentiment = ai_assistant.process_query(command)
        tts_wrapper(response)
        logging.info(f"인식된 개체: {entities}")
        logging.info(f"감성 분석 결과: {sentiment}")

        if learning_mode:
            tts_wrapper("응답이 적절했나요? '적절' 또는 '부적절'로 대답해주세요.")
            feedback = listen_for_feedback()

            if "부적절" in feedback.lower():
                tts_wrapper("새로운 응답을 말씀해 주세요.")
                new_response = listen_for_new_response()
                if new_response:
                    ai_assistant.learn_new_response(command, new_response)
                    tts_wrapper("새로운 응답을 학습했습니다. 감사합니다.")
                    ai_assistant.update_q_table(command, "say_sorry", -1, command)
                else:
                    tts_wrapper("새로운 응답을 학습하지 못했습니다. 죄송합니다.")
            else:
                tts_wrapper("감사합니다. 앞으로도 좋은 답변을 드리도록 노력하겠습니다.")
                ai_assistant.update_q_table(command, "use_best_response", 1, command)


def listen_for_feedback():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        logging.info("피드백 대기 중...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)

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
        tts_wrapper("죄송합니다. 응답을 이해하지 못했습니다. 다시 말씀해 주세요.")
        return listen_for_new_response()
    except sr.RequestError as e:
        logging.error(f"음성 인식 서비스 오류: {e}")
        tts_wrapper(
            "음성 인식 서비스에 문제가 발생했습니다. 나중에 다시 시도해 주세요."
        )
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
    """Windows 볼륨 조절"""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))

        current_volume = volume.GetMasterVolumeLevelScalar()
        new_volume = max(0.0, min(1.0, current_volume + change))
        volume.SetMasterVolumeLevelScalar(new_volume, None)

        tts_wrapper(f"볼륨을 {int(new_volume * 100)}%로 조절했습니다.")
    except Exception as e:
        logging.error(f"볼륨 조절 실패: {str(e)}")
        tts_wrapper("볼륨 조절에 실패했습니다.")


class VoiceRecognitionThread(QThread):
    result = Signal(str)
    listening_state_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.running = True
        self.selected_microphone = None
        self.microphone_index = None

        # 간단한 웨이크워드
        self.wake_detector = SimpleWakeWord(wake_words=["아리야", "시작"])

        # 마이크 초기화
        self.speech_recognizer = sr.Recognizer()
        self.microphone = sr.Microphone(device_index=self.microphone_index)

    def init_microphone(self):
        # 기본 마이크 사용
        logging.info("기본 오디오 입력 장치를 사용합니다.")

    def set_microphone(self, microphone):
        if self.selected_microphone != microphone:
            self.selected_microphone = microphone
            self.microphone_index = self.get_microphone_index(microphone)
            # 마이크 인덱스 업데이트
            self.microphone = sr.Microphone(device_index=self.microphone_index)

    def get_microphone_index(self, microphone_name):
        import speech_recognition as sr
        for index, name in enumerate(sr.Microphone.list_microphone_names()):
            if microphone_name in name:
                return index
        return None

    def run(self):
        try:
            logging.info("음성 감지 시작 (웨이크워드: 아리야, 시작)")
            while self.running:
                if self.wake_detector.listen_for_wake_word():
                    self.handle_wake_word()
                time.sleep(0.1)
        except Exception as e:
            logging.error(f"오류 발생: {str(e)}", exc_info=True)
        finally:
            self.cleanup()


    def handle_wake_word(self):
        logging.info("웨이크 워드 '아리야' 감지!")
        wake_responses = ["네?", "부르셨나요?"]
        response = random.choice(wake_responses)
        tts_wrapper(response)
        self.listening_state_changed.emit(True)
        self.recognize_speech()
        self.listening_state_changed.emit(False)

    def recognize_speech(self):
        try:
            with self.microphone as source:
                logging.info("말씀해 주세요...")
                audio = self.speech_recognizer.listen(source, timeout=5, phrase_time_limit=5)

            text = self.speech_recognizer.recognize_google(audio, language="ko-KR")
            logging.info(f"인식된 텍스트: {text}")
            self.result.emit(text)

        except sr.UnknownValueError:
            logging.warning("음성을 인식할 수 없습니다.")
        except sr.RequestError as e:
            logging.error(f"음성 인식 서비스 오류: {e}")
        except Exception as e:
            logging.error(f"음성 인식 중 오류: {str(e)}")

    def cleanup(self):
        logging.info("음성 인식 스레드 종료 중...")
        logging.info("음성 인식 스레드 종료 완료")

    def get_voice_feedback(self):
        pass

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
