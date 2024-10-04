#!/bin/bash

# 시스템 패키지 설치
echo "필요한 시스템 패키지를 설치합니다..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-pyaudio portaudio19-dev libatlas-base-dev

# 가상 환경이 없으면 생성 및 의존성 설치
if [ ! -d "ari" ]; then
    echo "가상 환경 'ari'를 생성합니다..."
    python3 -m venv ari

    echo "가상 환경을 활성화합니다..."
    source ari/bin/activate

    echo "Python 패키지를 설치합니다..."
    pip install --upgrade pip
    pip install -r requirements.txt

    deactivate
else
    echo "가상 환경 'ari'가 이미 존재합니다. 의존성 설치를 건너뜁니다."
fi

# 가상 환경 활성화
echo "가상 환경을 활성화합니다..."
source ari/bin/activate

# AriVoiceCommand 실행 (백그라운드에서)
echo "AriVoiceCommand를 백그라운드에서 실행합니다..."
./AriVoiceCommand &

# 가상 환경 비활성화
echo "가상 환경을 비활성화합니다..."
deactivate