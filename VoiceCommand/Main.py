import sys
import os
import setproctitle
import random
import time
import logging
from datetime import datetime
import gc
import psutil
import speech_recognition as sr
import warnings
import sounddevice as sd
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QMainWindow,
    QLabel,
    QPushButton,
    QComboBox,
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import (
    QThread,
    Signal,
    QTimer,
)
from ai_assistant import get_ai_assistant
from collections import deque
from VoiceCommand import (
    VoiceRecognitionThread,
    text_to_speech,
    TTSThread,
    ModelLoadingThread,
    CommandExecutionThread,
    set_ai_assistant,
)

# 전역 변수 선언
tts_model = None
speaker_ids = None
whisper_model = None
ai_assistant = None
icon_path = None
pulse = None
active_timer = None

warnings.filterwarnings("ignore", category=FutureWarning)
os.environ["SDL_VIDEODRIVER"] = "dummy"

sys.stdout.write("\x1b]2;Ari Voice Command\x07")

icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
if not os.path.exists(icon_path):
    print(f"경고: 아이콘 파일을 찾을 수 없습니다: {icon_path}")
    icon_path = None  # 아이콘 파일이 없을 경우 None으로


# 볼륨 제어를 위한 설정
def init_audio():
    try:
        sd.default.device = sd.default.device  # 기본 장치 설정
        logging.info("오디오 초기화 완료")
    except Exception as e:
        logging.error(f"오디오 초기화 실패: {str(e)}")


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

    def __init__(self, check_interval=5):
        super().__init__()
        self.check_interval = check_interval
        self.running = True
        self.process = psutil.Process()
        self.memory_history = deque(maxlen=10)  # 최근 10개의 메모리 사용량 기록
        self.last_gc_time = time.time()

    def get_memory_info(self):
        try:
            mem_info = self.process.memory_info()
            return mem_info.private / (1024 * 1024)  # Private Working Set in MB
        except:
            return 0

    def run(self):
        while self.running:
            current_memory = self.get_memory_info()
            self.memory_history.append(current_memory)

            if len(self.memory_history) >= 5:  # 최소 5개의 샘플이 있을 때
                avg_memory = sum(self.memory_history) / len(self.memory_history)
                if (
                    current_memory > avg_memory * 1.5
                    and time.time() - self.last_gc_time > 60
                ):
                    # 현재 메모리가 평균의 1.5배 이상이고, 마지막 GC로부터 1분 이상 지났을 때
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
    logging.info(f"가비지 컬렉션 완료. 메모리 사용량:")
    logging.info(f"  Private Working Set: {mem_info.private / (1024 * 1024):.2f} MB")
    logging.info(f"  RSS: {mem_info.rss / (1024 * 1024):.2f} MB")


def handle_command(result):
    # handle the command here
    pass


class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self, icon, parent=None):
        super(SystemTrayIcon, self).__init__(icon, parent)
        self.setToolTip(f"Ari Voice Command")

        self.menu = QMenu(parent)
        self.setContextMenu(self.menu)

        self.activated.connect(self.on_tray_icon_activated)

        self.exit_action = self.menu.addAction("종료")
        self.exit_action.triggered.connect(self.exit)

    def exit(self):
        QApplication.instance().quit()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.parent().show()
            self.parent().activateWindow()


def main():
    global ai_assistant, icon_path, tts_thread, pulse
    setproctitle.setproctitle("Ari Voice Command")
    try:
        setup_logging()
        logging.info("프로그램 시작")

        app = QApplication(sys.argv)

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logging.error("시스템 트레이를 사용할 수 없습니다.")
            sys.exit(1)

        app.setQuitOnLastWindowClosed(False)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        if not os.path.exists(icon_path):
            logging.warning("아이콘 파일이 없습니다. 기본 아이콘을 사용합니다.")
            icon_path = None

        tray_icon = SystemTrayIcon(QIcon(icon_path) if icon_path else QIcon())
        tray_icon.show()

        ai_assistant = get_ai_assistant()
        set_ai_assistant(ai_assistant)

        voice_thread = VoiceRecognitionThread()
        tts_thread = TTSThread()
        command_thread = CommandExecutionThread()

        voice_thread.result.connect(handle_command)
        voice_thread.start()
        tts_thread.start()
        command_thread.start()

        # 리소스 모니터링
        resource_monitor = ResourceMonitor()
        resource_monitor.gc_needed.connect(perform_gc)
        resource_monitor.start()
        
        gc_timer = QTimer()
        gc_timer.timeout.connect(perform_gc)
        gc_timer.start(5 * 60 * 1000)  # 5분마다 실행 (밀리초 단위)

        # 메인 루프
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("프로그램 종료 중...")
        finally:
            voice_thread.stop()
            voice_thread.wait()
            tts_thread.queue.put(None)
            command_thread.queue.put(None)
            tts_thread.wait()
            command_thread.wait()
            resource_monitor.stop()
            resource_monitor.wait()

        sys.exit(app.exec())

    except Exception as e:
        logging.error(f"예외 발생: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
