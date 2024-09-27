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
import time
import warnings
import pulsectl
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QMainWindow,
    QLabel,
    QPushButton,
    QComboBox,
)
from PySide6.QtGui import (
    QIcon,
    QAction,
)
from PySide6.QtCore import (
    QThread,
    Signal,
    QTimer,
)
from ai_assistant import get_ai_assistant
from collections import deque
from CharacterWidget import CharacterWidget
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

icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
if not os.path.exists(icon_path):
    print(f"경고: 아이콘 파일을 찾을 수 없습니다: {icon_path}")
    icon_path = None  # 아이콘 파일이 없을 경우 None으로


# 볼륨 제어를 위한 설정 (윈도우 전용)
pulse = pulsectl.Pulse('volume-control')


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


class MainWindow(QMainWindow):
    if os.name == 'nt':
        setproctitle.setproctitle("Ari Voice Command")
    
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
        self.voice_thread.listening_state_changed.connect(self.update_listening_state)

        self.voice_thread.start()
        self.tts_thread.start()
        self.command_thread.start()

        # GC 타이머 추가
        self.gc_timer = QTimer(self)
        self.gc_timer.timeout.connect(self.periodic_gc)
        self.gc_timer.start(5 * 60 * 1000)  # 5분마다 실행 (밀리초 단위)

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

    def show_window(self):
        self.show()
        self.activateWindow()

    def handle_voice_result(self, text):
        logging.info(f"인식된 명령: {text}")
        self.command_thread.execute(text)

    def update_listening_state(self, is_listening):
        for character in self.tray_icon.character_widgets:
            character.set_listening_state(is_listening)

    def periodic_gc(self):
        logging.info("주기적 가비지 컬렉션 실행")
        perform_gc()

    def show_speech_bubble(self, text):
        if hasattr(self.tray_icon, "character_widgets"):
            for character in self.tray_icon.character_widgets:
                character.show_speech_bubble(text)

    def hide_speech_bubble(self):
        if hasattr(self.tray_icon, "character_widgets"):
            for character in self.tray_icon.character_widgets:
                character.hide_speech_bubble()


def main():
	global ai_assistant, icon_path, tts_thread, pulse
	setproctitle.setproctitle("Ari Voice Command")
	try:
		setup_logging()
		logging.info("프로그램 시작")

		# 리눅스에서 콘솔 제목 설정
		sys.stdout.write("\x1b]2;Ari Voice Command\x07")

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
			set_ai_assistant(ai_assistant)  # VoiceCommand 모듈에 ai_assistant 전달
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
		app.aboutToQuit.connect(pulse.close)  # PulseAudio 연결 종료

		sys.exit(app.exec())
	except Exception as e:
		logging.error(f"예외 발생: {str(e)}", exc_info=True)
		sys.exit(1)


if __name__ == "__main__":
    main()
