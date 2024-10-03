# 베이스 이미지 선택
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libatlas-base-dev \
    firefox-esr \
    libasound2-dev \
    git && \
    rm -rf /var/lib/apt/lists/*

# 프로젝트 파일 복사
COPY . .

# Python 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 환경 변수 설정 (필요한 경우)
ENV SDL_VIDEODRIVER=dummy

# 애플리케이션 실행
CMD ["python", "Main.py"]