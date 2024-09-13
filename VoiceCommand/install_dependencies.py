import subprocess
import sys
import os


def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def main():
    print("필요한 패키지를 설치합니다...")

    # requirements.txt 파일 생성
    requirements = [
        "pycaw",
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
        "comtypes",
        "pywin32",
    ]

    with open("requirements.txt", "w") as f:
        for req in requirements:
            f.write(f"{req}\n")

    print("requirements.txt 파일을 생성했습니다.")

    # requirements.txt 파일에서 패키지 설치
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        )
    except subprocess.CalledProcessError:
        print("requirements.txt 파일을 찾을 수 없거나 설치 중 오류가 발생했습니다.")
        return

    print("MeloTTS를 설치합니다...")

    # MeloTTS 설치
    try:
        install("git+https://github.com/myshell-ai/MeloTTS.git")
    except subprocess.CalledProcessError:
        print("MeloTTS 설치 중 오류가 발생했습니다.")
        return

    print("추가 패키지를 설치합니다...")

    # 추가 패키지 설치
    additional_packages = ["pyinstaller", "python-dotenv"]

    for package in additional_packages:
        try:
            install(package)
        except subprocess.CalledProcessError:
            print(f"{package} 설치 중 오류가 발생했습니다.")
            return

    print("모든 패키지가 성공적으로 설치되었습니다.")

    # 설치 완료 후 사용자에게 알림
    input("설치가 완료되었습니다. 엔터 키를 눌러 종료하세요...")


if __name__ == "__main__":
    main()
