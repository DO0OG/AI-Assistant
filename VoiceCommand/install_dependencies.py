import subprocess
import sys


def install_dependencies():
    # requirements.txt 파일에서 의존성 읽기
    with open("requirements.txt", "r") as f:
        requirements = f.read().splitlines()

    # 각 의존성 설치
    for package in requirements:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"{package} 설치 완료")
        except subprocess.CalledProcessError:
            print(f"{package} 설치 실패")


if __name__ == "__main__":
    install_dependencies()
