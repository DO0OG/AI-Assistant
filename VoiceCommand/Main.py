import sys
import os
import time
import logging
from datetime import datetime
import gc
import psutil
import warnings
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QDialog
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QObject, Signal, QTimer
from settings_dialog import SettingsDialog
from ai_assistant import get_ai_assistant
from character_widget import CharacterWidget
from collections import deque
from VoiceCommand import (
    VoiceRecognitionThread,
    tts_wrapper,
    TTSThread,
    # ModelLoadingThread 제거
    CommandExecutionThread,
    set_ai_assistant,
)
import json
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

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
        self.should_exit = False

        self.menu = QMenu(parent)
        self.setContextMenu(self.menu)

        # 설정 메뉴 추가
        self.settings_action = self.menu.addAction("설정")
        self.settings_action.triggered.connect(self.open_settings)

        self.menu.addSeparator()

        self.exit_action = self.menu.addAction("종료")
        self.exit_action.triggered.connect(self.exit)

    def open_settings(self):
        """설정 창 열기"""
        dialog = SettingsDialog()
        if dialog.exec() == QDialog.Accepted:
            # 설정 변경 후 TTS 재초기화
            from VoiceCommand import initialize_tts
            initialize_tts()
            logging.info("설정이 저장되고 TTS가 재초기화되었습니다.")

    def exit(self):
        self.should_exit = True
        QApplication.instance().quit()


class AriCore(QObject):
    def __init__(self):
        super().__init__()
        self.voice_thread = VoiceRecognitionThread()
        self.tts_thread = TTSThread()
        self.command_thread = CommandExecutionThread()
        self.resource_monitor = ResourceMonitor()
        logging.info("AriCore 초기화 완료")

        self.init_microphone()
        self.init_threads()
        self.init_connections()
        self.load_settings()

        self.file_observer = start_file_watcher()
        logging.info("파일 감시 시작")

    def init_threads(self):
        self.voice_thread.start()
        self.tts_thread.start()
        self.command_thread.start()
        self.resource_monitor.gc_needed.connect(perform_gc)

    def init_connections(self):
        self.voice_thread.result.connect(self.handle_voice_result)

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
        # 기본 마이크 사용
        logging.info("기본 마이크를 사용합니다.")
        self.voice_thread.set_microphone(None)

    def save_settings(self, microphone):
        settings = {"microphone": microphone}
        with open("settings.json", "w") as f:
            json.dump(settings, f)

    def handle_voice_result(self, text):
        logging.info(f"인식된 명령: {text}")
        self.command_thread.execute(text)

    def cleanup(self):
        self.voice_thread.stop()
        self.voice_thread.wait()
        self.tts_thread.queue.put(None)
        self.command_thread.queue.put(None)
        self.tts_thread.wait()
        self.command_thread.wait()
        self.resource_monitor.stop()
        logging.info("AriCore 정리 완료")
        self.file_observer.stop()
        self.file_observer.join()
        logging.info("파일 감시 종료")


class FileChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            logging.info(f"파일 {event.src_path}가 수정되었습니다. 프로그램을 재시작합니다...")
            os.execv(sys.executable, ['python'] + sys.argv)


def start_file_watcher():
    event_handler = FileChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.start()
    return observer


def main():
    global ai_assistant, icon_path
    ari_core = None
    character = None
    tray_icon = None
    try:
        setup_logging()
        logging.info("프로그램 시작")

        app = QApplication(sys.argv)

        # AI 어시스턴트 초기화
        ai_assistant = get_ai_assistant()
        set_ai_assistant(ai_assistant)

        use_system_tray = QSystemTrayIcon.isSystemTrayAvailable()

        if use_system_tray:
            app.setQuitOnLastWindowClosed(False)
            icon = QIcon(icon_path) if icon_path else QIcon()
            tray_icon = SystemTrayIcon(icon)
            tray_icon.show()
        else:
            logging.warning("시스템 트레이를 사용할 수 없습니다. 콘솔 모드로 실행합니다.")

        ari_core = AriCore()

        # 캐릭터 위젯 생성
        character = CharacterWidget()

        tts_wrapper("안녕하세요")

        # 메인 이벤트 루프 실행
        while True:
            app.processEvents()  # Qt 이벤트 처리

            # 종료 플래그 확인
            if tray_icon and tray_icon.should_exit:
                logging.info("종료 요청됨")
                break

            time.sleep(0.1)  # CPU 사용량을 줄이기 위한 짧은 대기

    except KeyboardInterrupt:
        logging.info("프로그램 종료")
    except Exception as e:
        logging.error(f"예외 발생: {str(e)}", exc_info=True)
    finally:
        if character:
            character.cleanup()
        if ari_core:
            ari_core.cleanup()

if __name__ == "__main__":
    main()
