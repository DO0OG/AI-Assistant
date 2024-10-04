import sys
import os
import time
import logging
from datetime import datetime
import gc
import psutil
import speech_recognition as sr
import warnings
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
from PySide6.QtCore import QThread, Signal, QTimer
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
    icon_path = None  # 아이콘 파일이 없을 경우 None으로


# 로그 설정
def setup_logging():
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"ari_log_{current_time}.log")

    # 기존 핸들러 제거
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

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
            return mem_info.rss / (1024 * 1024)  # RSS in MB
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
    logging.info(f"  RSS: {mem_info.rss / (1024 * 1024):.2f} MB")


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
        self.parent().close_application.emit()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.parent().show()
            self.parent().activateWindow()


class MainWindow(QMainWindow):
    close_application = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("MainWindow")
        self.setWindowTitle("Ari Voice Command")
        self.setGeometry(100, 100, 300, 250)
        self.setFixedSize(300, 200)

        global icon_path
        if icon_path:
            self.tray_icon = SystemTrayIcon(QIcon(icon_path), self)
        else:
            self.tray_icon = SystemTrayIcon(QIcon(), self)  # 빈 아이콘으로 생성
        self.tray_icon.show()

        # voice_thread를 먼저 초기화
        self.voice_thread = VoiceRecognitionThread()
        self.tts_thread = TTSThread()
        self.command_thread = CommandExecutionThread()

        self.initUI()
        self.init_pipewire_microphone()  # PipeWire 마이크 초기화 추가

        self.model_loading_thread = ModelLoadingThread()
        self.model_loading_thread.finished.connect(self.on_model_loaded)
        self.model_loading_thread.start()
        self.tray_icon.showMessage(
            "Ari", "TTS 및 Whisper 모델 로딩 중...", QSystemTrayIcon.Information, 3000
        )

        self.resource_monitor = ResourceMonitor()
        self.resource_monitor.gc_needed.connect(perform_gc)
        self.resource_monitor.start()

        self.voice_thread.result.connect(self.handle_voice_result)

        self.voice_thread.start()
        self.tts_thread.start()
        self.command_thread.start()

        # GC 타이머 추가
        self.gc_timer = QTimer(self)
        self.gc_timer.timeout.connect(self.periodic_gc)
        self.gc_timer.start(5 * 60 * 1000)  # 5분마다 실행 (밀리초 단위)

        self.close_application.connect(self.cleanup_and_exit)

    def initUI(self):
        self.microphone_label = QLabel("마이크:", self)
        self.microphone_label.setGeometry(20, 50, 80, 30)

        self.microphone_combo = QComboBox(self)
        self.microphone_combo.setGeometry(100, 50, 180, 30)
        
        # PipeWire 마이크 목록 가져오기
        pipewire_devices = self.voice_thread.get_pipewire_devices()
        self.microphone_combo.addItems(pipewire_devices)
        
        # 첫 번째 PipeWire 마이크 선택
        if pipewire_devices:
            self.microphone_combo.setCurrentIndex(0)
            self.voice_thread.set_microphone(pipewire_devices[0])

        self.save_button = QPushButton("저장", self)
        self.save_button.setGeometry(100, 100, 100, 30)
        self.save_button.clicked.connect(self.save_settings)

        self.microphone_combo.currentIndexChanged.connect(self.update_microphone)

    def init_pipewire_microphone(self):
        if self.microphone_combo.count() > 0:
            selected_microphone = self.microphone_combo.currentText()
            if hasattr(self, "voice_thread") and self.voice_thread:
                self.voice_thread.set_microphone(selected_microphone)
            logging.info(f"PipeWire 마이크 초기화: {selected_microphone}")

    def update_microphone(self):
        selected_microphone = self.microphone_combo.currentText()
        if hasattr(self, "voice_thread") and self.voice_thread:
            self.voice_thread.set_microphone(selected_microphone)
        logging.info(f"마이크 변경: {selected_microphone}")

    def save_settings(self):
        selected_microphone = self.microphone_combo.currentText()
        logging.info(f"선택된 마이크: {selected_microphone}")
        try:
            if hasattr(self, "voice_thread") and self.voice_thread:
                self.voice_thread.set_microphone(selected_microphone)
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
        event.ignore()
        self.hide()

    def on_model_loaded(self):
        logging.info("모델 로딩이 완료되었습니다.")
        # 로딩 완료 알림
        self.tray_icon.showMessage(
            "Ari", "TTS 및 Whisper 모델 로딩 완료!", QSystemTrayIcon.Information, 3000
        )

    def handle_voice_result(self, text):
        logging.info(f"인식된 명령: {text}")
        self.command_thread.execute(text)

    def periodic_gc(self):
        logging.info("주기적 가비지 컬렉션 실행")
        perform_gc()

    def cleanup_and_exit(self):
        self.voice_thread.stop()
        self.voice_thread.wait()
        self.tts_thread.queue.put(None)
        self.command_thread.queue.put(None)
        self.tts_thread.wait()
        self.command_thread.wait()
        self.resource_monitor.stop()
        self.resource_monitor.wait()
        QApplication.instance().quit()


def main():
    global ai_assistant, icon_path, tts_thread
    try:
        setup_logging()
        logging.info("프로그램 시작")

        app = QApplication(sys.argv)
        
        # AI 어시스턴트 초기화 또는 로드
        model_path = "./saved_model"
        if os.path.exists(model_path) and os.path.isfile(os.path.join(model_path, 'model_weights.pth')):
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

        set_ai_assistant(ai_assistant)  # VoiceCommand 모듈에 ai_assistant 전달

        main_window = MainWindow()
        main_window.ai_assistant = ai_assistant  # MainWindow 인스턴스에 ai_assistant 할당
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

        # 마이크 설정 변경 시 음성 인식 스레드에 알림
        def update_microphone():
            selected_microphone = main_window.microphone_combo.currentText()
            main_window.voice_thread.set_microphone(selected_microphone)

        main_window.save_button.clicked.connect(update_microphone)

        sys.exit(app.exec())
    except Exception as e:
        logging.error(f"예외 발생: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
