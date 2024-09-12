import subprocess
import sys


def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def main():
    print("필요한 패키지를 설치합니다...")

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

    print("모든 패키지가 성공적으로 설치되었습니다.")


if __name__ == "__main__":
    main()
