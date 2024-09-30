import subprocess
import sys
import os


def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def create_requirements_file():
    requirements = [
        "sounddevice",
        "keyboard",
        "openai-whisper",
        "SpeechRecognition",
        "PySide6",
        "pydub",
        "torch",
        "selenium",
        "webdriver_manager",
        "transformers",
        "numpy",
        "pyaudio",
        "pvporcupine",
        "geopy",
        "requests",
        "psutil",
        "urllib3",
        "datetime",
        "python-dotenv",
        "scikit-learn",
        "joblib",
        "git+https://github.com/myshell-ai/MeloTTS.git",
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
    print("sudo apt-get install python3-pyaudio portaudio19-dev libatlas-base-dev")
    print("sudo apt-get install firefox-esr")  # Firefox 설치 (웹 자동화용)
    print("sudo apt-get install libasound2-dev")  # ALSA 개발 라이브러리 설치
    print("sudo apt-get install git")  # Git 설치 (MeloTTS 설치에 필요)

    # 폰트 설치 안내
    print("\n'DNFBitBitv2.ttf' 폰트 파일을 프로젝트 디렉토리에 복사해주세요.")

    # 설정 파일 생성 안내
    print("\n'config.json' 파일을 생성하고 필요한 API 키를 입력해주세요.")

if __name__ == "__main__":
    main()
