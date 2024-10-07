#!/bin/bash

# 잠시 대기 (그래픽 환경이 완전히 로드될 때까지)
sleep 5

# Ari 디렉토리로 이동
cd /home/laleme/Ari

# 가상환경 활성화
source ari/bin/activate

# Main.py 실행
python3 Main.py

export DISPLAY=:0
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/$(id -u)