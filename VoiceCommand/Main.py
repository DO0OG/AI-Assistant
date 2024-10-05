import sys
import os
import time
import logging
from datetime import datetime
import gc
import psutil
import warnings
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon
from PySide6.QtCore import QObject, Signal, QTimer
from ai_assistant import AdvancedAIAssistant, get_ai_assistant
from collections import deque
from VoiceCommand import (
    VoiceRecognitionThread,
    text_to_speech,
    TTSThread,
    ModelLoadingThread,
    CommandExecutionThread,
    set_ai_assistant,
)
import json

# 전역 변수 선언
tts_model = None
speaker_ids = None
whisper_model = None
ai_assistant = None
icon_path = None
active_timer = None

warnings.filterwarnings("ignore", category=FutureWarning)
os.environ["SDL_VIDEODRIVER"] = "dummy"

icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
if not os.path.exists(icon_path):
    print(f"경고: 아이콘 파일을 찾을 수 없습니다: {icon_path}")
    icon_path = None


# 로그 설정
def setup_logging():
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"ari_log_{current_time}.log")

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


# 리소스 모니터링 스레드
class ResourceMonitor(QObject):
    gc_needed = Signal()

    def __init__(self, check_interval=5):
        super().__init__()
        self.check_interval = check_interval
        self.running = True
        self.process = psutil.Process()
        self.memory_history = deque(maxlen=10)
        self.last_gc_time = time.time()

    def get_memory_info(self):
        try:
            mem_info = self.process.memory_info()
            return mem_info.rss / (1024 * 1024)
        except:
            return 0

    def run(self):
        while self.running:
            current_memory = self.get_memory_info()
            self.memory_history.append(current_memory)

            if len(self.memory_history) >= 5:
                avg_memory = sum(self.memory_history) / len(self.memory_history)
                if (
                    current_memory > avg_memory * 1.5
                    and time.time() - self.last_gc_time > 60
                ):
                    self.gc_needed.emit()
                    self.last_gc_time = time.time()

            time.sleep(self.check_interval)

    def stop(self):
        self.running = False


# 가비지 컬렉션 실행
def perform_gc():
    logging.info("가비지 컬렉션 실행 중...")
    gc.collect()
    process = psutil.Process()
    mem_info = process.memory_info()
    logging.info(
        f"가비지 컬렉션 완료. 메모리 사용량: RSS: {mem_info.rss / (1024 * 1024):.2f} MB"
    )


class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self, icon, parent=None):
        super(SystemTrayIcon, self).__init__(icon, parent)
        self.setToolTip(f"Ari Voice Command")

        self.menu = QMenu(parent)
        self.setContextMenu(self.menu)

        self.exit_action = self.menu.addAction("종료")
        self.exit_action.triggered.connect(self.exit)

    def exit(self):
        QApplication.instance().quit()


class AriCore(QObject):
    def __init__(self):
        super().__init__()
        self.voice_thread = VoiceRecognitionThread()
        self.tts_thread = TTSThread()
        self.command_thread = CommandExecutionThread()
        self.model_loading_thread = ModelLoadingThread()
        self.resource_monitor = ResourceMonitor()

        self.init_microphone()
        self.init_threads()
        self.init_connections()
        self.load_settings()

    def init_threads(self):
        self.voice_thread.start()
        self.tts_thread.start()
        self.command_thread.start()
        self.model_loading_thread.start()
        self.resource_monitor.gc_needed.connect(perform_gc)

    def init_connections(self):
        self.voice_thread.result.connect(self.handle_voice_result)
        self.model_loading_thread.finished.connect(self.on_model_loaded)

    def load_settings(self):
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
            selected_microphone = settings.get("microphone", "")
            if selected_microphone:
                self.voice_thread.set_microphone(selected_microphone)
        except FileNotFoundError:
            logging.warning("설정 파일을 찾을 수 없습니다. 기본 설정을 사용합니다.")
        except json.JSONDecodeError:
            logging.error(
                "설정 파일을 읽는 중 오류가 발생했습니다. 기본 설정을 사용합니다."
            )

    def init_microphone(self):
        max_attempts = 5
        attempt = 0
        while attempt < max_attempts:
            pipewire_devices = self.voice_thread.get_pipewire_devices()
            if pipewire_devices:
                for device in pipewire_devices:
                    if "voicehat" in device.lower():
                        self.voice_thread.set_microphone(device)
                        logging.info(f"마이크 초기화 성공: {device}")
                        return
                self.voice_thread.set_microphone(pipewire_devices[0])
                logging.info(f"마이크 초기화 성공 (기본 장치): {pipewire_devices[0]}")
                return
            attempt += 1
            logging.warning(
                f"마이크를 찾을 수 없습니다. 재시도 중... (시도 {attempt}/{max_attempts})"
            )
            time.sleep(2)
        logging.error("마이크를 찾을 수 없습니다. 기본 오디오 입력을 사용합니다.")
        self.voice_thread.set_microphone(None)

    def save_settings(self, microphone):
        settings = {"microphone": microphone}
        with open("settings.json", "w") as f:
            json.dump(settings, f)

    def handle_voice_result(self, text):
        logging.info(f"인식된 명령: {text}")
        self.command_thread.execute(text)

    def on_model_loaded(self):
        logging.info("모델 로딩이 완료되었습니다.")

    def cleanup(self):
        self.voice_thread.stop()
        self.voice_thread.wait()
        self.tts_thread.queue.put(None)
        self.command_thread.queue.put(None)
        self.tts_thread.wait()
        self.command_thread.wait()
        self.resource_monitor.stop()


def main():
    global ai_assistant, icon_path, tts_thread
    try:
        setup_logging()
        logging.info("프로그램 시작")

        app = QApplication(sys.argv)

        model_path = "./saved_model"
        if os.path.exists(model_path) and os.path.isfile(
            os.path.join(model_path, "model_weights.pth")
        ):
            try:
                logging.info("기존 모델을 로드합니다.")
                ai_assistant = AdvancedAIAssistant.load_model(model_path)
                logging.info("모델 로드 완료")
            except Exception as e:
                logging.error(f"모델 로드 중 오류 발생: {str(e)}")
                logging.info("새로운 AI 어시스턴트를 초기화합니다.")
                ai_assistant = get_ai_assistant()
        else:
            logging.info("저장된 모델이 없습니다. 새로운 AI 어시스턴트를 초기화합니다.")
            ai_assistant = get_ai_assistant()

        set_ai_assistant(ai_assistant)

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logging.error("시스템 트레이를 사용할 수 없습니다.")
            sys.exit(1)

        app.setQuitOnLastWindowClosed(False)

        icon = QIcon(icon_path) if icon_path else QIcon()
        tray_icon = SystemTrayIcon(icon)
        tray_icon.show()

        ari_core = AriCore()

        app.aboutToQuit.connect(ari_core.cleanup)

        sys.exit(app.exec())
    except Exception as e:
        logging.error(f"예외 발생: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
