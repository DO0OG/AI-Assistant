import subprocess
import sys
import os


def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def create_requirements_file():
    requirements = [
        "pulsectl",
        "keyboard",
        "openai-whisper",
        "SpeechRecognition",
        "PySide6",
        "pydub",
        "torch",
        "selenium",
        "webdriver_manager",
        "transformers",
        "llama-cpp-python",
        "numpy",
        "pyaudio",
        "pvporcupine",
        "geopy",
        "requests",
        "psutil",
        "setproctitle",
        "urllib3",
        "datetime",
        "python-dotenv",
    ]

    with open("requirements.txt", "w") as f:
        for req in requirements:
            f.write(f"{req}\n")


def main():
    print("필요한 패키지를 설치합니다...")

    # requirements.txt 파일 생성
    create_requirements_file()
    print("requirements.txt 파일을 생성했습니다.")

    # requirements.txt 파일에서 패키지 설치
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        )
    except subprocess.CalledProcessError:
        print("requirements.txt 파일을 찾을 수 없거나 설치 중 오류가 발생했습니다.")
        return

    print("모든 패키지가 성공적으로 설치되었습니다.")

    # 시스템 패키지 설치 안내
    print("\n일부 패키지는 시스템 패키지 관리자를 통해 설치해야 할 수 있습니다.")
    print("다음 명령어를 실행하여 필요한 시스템 패키지를 설치하세요:")
    print("sudo apt-get update")
    print("sudo apt-get install python3-pyaudio portaudio19-dev")

if __name__ == "__main__":
    main()
