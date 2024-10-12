import os
import random
import webbrowser
import time
import logging
from urllib.parse import quote_plus
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
import warnings
import speech_recognition as sr
import torch
import pyaudio
import sounddevice as sd
import subprocess
import pulsectl
import numpy as np
import threading
from datetime import datetime, timedelta
from queue import Queue
import requests
import math
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, Signal
from pydub import AudioSegment
from pydub.playback import play
from Config import use_api
import pvporcupine
from vosk import Model, KaldiRecognizer
import json
import asyncio
from edge_tts import Communicate
from pydub import AudioSegment
from pydub.playback import play
import io
import yt_dlp
import vlc
import logging
from scipy import signal
from LEDController import voice_recognition_start, tts_start, idle
from file_share_server import send_file
from Config import get_home_assistant_url, get_home_assistant_token

# 전역 변수 선언
ai_assistant = None
icon_path = None
pulse = None
active_timer = None
active_shutdown_timer = None
learning_mode = False

player = None
stop_event = threading.Event()
playlist = []
current_track_index = 0
paused = False
current_url = None
current_time = 0
auto_play = True  # 자동 재생 플래그 추가


def set_ai_assistant(assistant):
    global ai_assistant
    ai_assistant = assistant


warnings.filterwarnings("ignore", category=DeprecationWarning)
device = "cuda" if torch.cuda.is_available() else "cpu"


class VoskRecognizer:
    def __init__(self, model_path):
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, 16000)
        self.mic = pyaudio.PyAudio()
        self.stream = self.mic.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=8192,
        )
        self.stream.start_stream()

    def listen(self):
        while True:
            data = self.stream.read(4096)
            if len(data) == 0:
                break
            if self.recognizer.AcceptWaveform(data):
                result = self.recognizer.Result()
                return result

    def close(self):
        self.stream.stop_stream()
        self.stream.close()
        self.mic.terminate()


async def text_to_speech(text, voice="ko-KR-SunHiNeural", rate="+0%", volume="+0%"):
    try:
        communicate = Communicate(text, voice, rate=rate, volume=volume)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]

        # TTS 재생 전에 음성 인식을 비활성화
        app = QApplication.instance()
        main_window = next(
            (w for w in app.topLevelWidgets() if w.objectName() == "MainWindow"), None
        )
        if (
            main_window
            and hasattr(main_window, "voice_thread")
            and main_window.voice_thread
        ):
            main_window.voice_thread.is_tts_playing = True

        # 오디오 재생 (MP3 형식으로 처리)
        audio = AudioSegment.from_mp3(io.BytesIO(audio_data))
        
        # 볼륨 줄이기
        reduced_volume = audio - 3
        
        play(reduced_volume)

        # TTS 재생 후에 음성 인식을 다시 활성화
        if (
            main_window
            and hasattr(main_window, "voice_thread")
            and main_window.voice_thread
        ):
            main_window.voice_thread.is_tts_playing = False

    except Exception as e:
        logging.error(f"TTS 처리 중 오류 발생: {str(e)}")


def tts_wrapper(text, voice="ko-KR-SunHiNeural", rate="+0%", volume="+0%"):
    tts_start()  # TTS 시작 시 LED 상태 변경
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(text_to_speech(text, voice, rate, volume))
    idle()  # TTS 종료 후 LED 상태를 기본으로 변경


def shutdown_computer():
    os.system("sudo shutdown -h now")


def cancel_timer():
    global active_timer, active_shutdown_timer
    if active_timer:
        active_timer["timer"].cancel()
        active_timer = None
        tts_wrapper("타이머가 취소되었습니다.")
    if active_shutdown_timer:
        active_shutdown_timer["timer"].cancel()
        active_shutdown_timer = None
        tts_wrapper("컴퓨터 종료 타이머가 취소되었습니다.")
    if not active_timer and not active_shutdown_timer:
        tts_wrapper("현재 실행 중인 타이머가 없습니다.")


def set_timer(minutes):
    global active_timer

    def timer_thread():
        global active_timer
        if active_timer and datetime.now() >= active_timer["end_time"]:
            tts_wrapper(f"{minutes}분 타이머가 완료되었습니다.")
            active_timer = None
        elif active_timer:
            # 1초마다 확인하도록 새로운 타이머 설정
            threading.Timer(1, timer_thread).start()

    if active_timer:
        active_timer["timer"].cancel()

    end_time = datetime.now() + timedelta(minutes=minutes)
    active_timer = {"timer": threading.Timer(1, timer_thread), "end_time": end_time}
    active_timer["timer"].start()
    tts_wrapper(f"{minutes}분 타이머를 설정했습니다.")


def set_shutdown_timer(minutes):
    global active_shutdown_timer

    def shutdown_timer_thread():
        global active_shutdown_timer
        if (
            active_shutdown_timer
            and datetime.now() >= active_shutdown_timer["end_time"]
        ):
            tts_wrapper(f"{minutes}분이 지났습니다. 컴퓨터를 종료합니다.")
            shutdown_computer()
            active_shutdown_timer = None
        elif active_shutdown_timer:
            # 1초마다 확인하도록 새로운 타이머 설정
            threading.Timer(1, shutdown_timer_thread).start()

    if active_shutdown_timer:
        active_shutdown_timer["timer"].cancel()

    end_time = datetime.now() + timedelta(minutes=minutes)
    active_shutdown_timer = {
        "timer": threading.Timer(1, shutdown_timer_thread),
        "end_time": end_time,
    }
    active_shutdown_timer["timer"].start()
    tts_wrapper(f"{minutes}분 후에 컴퓨터를 종료하도록 설정했습니다.")


def open_website(url):
    webbrowser.open(url)
    logging.info(f"웹사이트 열기: {url}")


def search_youtube(query):
    search_url = f"https://www.youtube.com/results?search_query={query}"
    response = requests.get(search_url)
    
    start = response.text.find('var ytInitialData = ') + len('var ytInitialData = ')
    end = response.text.find(';</script>', start)
    json_str = response.text[start:end]
    data = json.loads(json_str)

    videos = data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']
    
    results = []
    for video in videos:
        if 'videoRenderer' in video:
            video_id = video['videoRenderer']['videoId']
            title = video['videoRenderer']['title']['runs'][0]['text']
            results.append((f"https://www.youtube.com/watch?v={video_id}", title))
            if len(results) == 5:  # 상위 5개 결과만 가져옵니다
                break
    
    return results

def play_youtube_audio(url, start_time=0):
    global player, stop_event, paused, current_url, current_time, auto_play
    stop_event.clear()
    paused = False
    current_url = url
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = info['url']
    
    instance = vlc.Instance('--no-video')
    player = instance.media_player_new()
    media = instance.media_new(audio_url)
    player.set_media(media)
    player.play()
    
    player.set_time(int(start_time * 1000))
    
    # 볼륨을 50%로 설정
    player.audio_set_volume(50)
    
    while not stop_event.is_set():
        state = player.get_state()
        if state == vlc.State.Playing:
            current_time = player.get_time() / 1000
        if state == vlc.State.Ended:
            break
        time.sleep(1)
    
    if not stop_event.is_set() and not paused and auto_play:
        play_next_track()


def search_and_play_youtube(query, play=True):
    global playlist, current_track_index, auto_play
    try:
        results = search_youtube(query)
        if results:
            playlist = results
            current_track_index = 0
            auto_play = play  # 검색 후 자동 재생 여부 설정
            if play:
                video_url, title = playlist[current_track_index]
                tts_wrapper(f"{title} 오디오를 재생합니다.")
                threading.Thread(target=play_youtube_audio, args=(video_url, 0)).start()
            else:
                video_url, title = playlist[current_track_index]
                subprocess.Popen(["chromium-browser", video_url])
                tts_wrapper(f"{title} 검색 결과를 열었습니다.")
            logging.info(f"유튜브 URL: {video_url}")
        else:
            tts_wrapper("검색 결과를 찾을 수 없습니다.")
    except Exception as e:
        logging.error(f"유튜브 검색 중 오류 발생: {str(e)}")
        tts_wrapper("유튜브 검색 중 오류가 발생했습니다.")


def stop_youtube_playback():
    global stop_event, player, paused, current_url, current_time, auto_play
    stop_event.set()
    if player:
        player.stop()
    paused = False
    current_url = None
    current_time = 0
    auto_play = False  # 재생 중지 시 자동 재생 비활성화
    tts_wrapper("유튜브 재생을 중지했습니다.")


def pause_youtube_playback():
    global player, paused, current_time
    if player and not paused:
        player.pause()
        current_time = player.get_time() / 1000  # 현재 시간을 초 단위로 저장
        paused = True
        tts_wrapper("재생을 일시 중지했습니다.")
        logging.info(f"일시 정지됨. 현재 시간: {current_time}초")
    else:
        tts_wrapper("재생 중인 오디오가 없습니다.")


def resume_youtube_playback():
    global player, paused, current_url, current_time
    if player and paused:
        player.play()
        player.set_time(int(current_time * 1000))  # 저장된 시간부터 재생 시작
        paused = False
        tts_wrapper("재생을 재개합니다.")
        logging.info(f"재생 재개됨. 시작 시간: {current_time}초")
    elif not player or not current_url:
        tts_wrapper("재생할 오디오가 없습니다.")
    else:
        tts_wrapper("이미 재생 중입니다.")


def play_next_track():
    global current_track_index, playlist, player, stop_event
    if playlist and len(playlist) > 1:
        stop_youtube_playback()  # 현재 재생 중인 곡 중지
        current_track_index = (current_track_index + 1) % len(playlist)
        video_url, title = playlist[current_track_index]
        tts_wrapper(f"다음 곡 {title}을 재생합니다.")
        threading.Thread(target=play_youtube_audio, args=(video_url, 0)).start()
    else:
        tts_wrapper("재생 목록이 끝났습니다.")
        stop_youtube_playback()


def play_previous_track():
    global current_track_index, playlist, player, stop_event
    if playlist:
        stop_youtube_playback()  # 현재 재생 중인 곡 중지
        current_track_index = (current_track_index - 1) % len(playlist)
        video_url, title = playlist[current_track_index]
        tts_wrapper(f"이전 곡 {title}을 재생합니다.")
        threading.Thread(target=play_youtube_audio, args=(video_url, 0)).start()
    else:
        tts_wrapper("재생 목록이 비어있습니다.")


def shuffle_playlist():
    global playlist, current_track_index
    if playlist:
        random.shuffle(playlist)
        current_track_index = 0
        video_url, title = playlist[current_track_index]
        tts_wrapper(f"플레이리스트를 섞었습니다. {title}을 재생합니다.")
        threading.Thread(target=play_youtube_audio, args=(video_url,)).start()


def get_current_time():
    now = datetime.now()
    return now.strftime("%H시 %M분")


def get_current_location():
    try:
        # 외부 IP를 기반으로 위치 정보 가져오기
        ip_response = requests.get("https://ipapi.co/json/")
        ip_data = ip_response.json()
        latitude = ip_data.get("latitude", 37.5665)  # 기본값은 서울의 위도
        longitude = ip_data.get("longitude", 126.9780)  # 기본값은 서울의 경도

        logging.info(f"IP 기반 위치: 위도 {latitude}, 경도 {longitude}")

        # 한국 내 위치인지 확인
        if 33 <= latitude <= 38 and 124 <= longitude <= 132:
            return latitude, longitude
        else:
            logging.warning("현재 위치가 한국 밖입니다. 서울의 좌표를 사용합니다.")
            return 37.5665, 126.9780  # 서울의 위도, 경도
    except Exception as e:
        logging.error(f"위치 정보 가져오기 실패: {str(e)}")
        return 37.5665, 126.9780  # 오류 발생 시 서울의 좌표 반환


def get_weather_info(lat, lon):
    base_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
    service_key = use_api("weather_api_key")

    now = datetime.now()
    base_date = now.strftime("%Y%m%d")
    
    # 단기예보 발표 시간에 맞춰 base_time 설정
    forecast_times = ['0200', '0500', '0800', '1100', '1400', '1700', '2000', '2300']
    base_time = max([t for t in forecast_times if now.strftime("%H%M") > t] or ['2300'])
    
    # 만약 선택된 시간이 '2300'이고 현재 시간이 00:00 ~ 02:00 사이라면 어제 날짜의 23:00 발표 사용
    if base_time == '2300' and now.strftime("%H%M") < '0200':
        base_date = (now - timedelta(days=1)).strftime("%Y%m%d")

    nx, ny = convert_coord(lat, lon)

    # 초단기실황 조회
    ultra_srt_ncst_url = f"{base_url}/getUltraSrtNcst"
    ultra_srt_ncst_params = {
        "serviceKey": service_key,
        "pageNo": "1",
        "numOfRows": "1000",
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": str(nx),
        "ny": str(ny),
    }

    try:
        # 초단기실황 데이터 가져오기
        ultra_srt_ncst_response = requests.get(ultra_srt_ncst_url, params=ultra_srt_ncst_params)
        ultra_srt_ncst_response.raise_for_status()
        logging.info(f"초단기실황 API 응답: {ultra_srt_ncst_response.text}")
        ultra_srt_ncst_data = ultra_srt_ncst_response.json()

        # 초단기실황 데이터 처리
        if 'response' not in ultra_srt_ncst_data or 'body' not in ultra_srt_ncst_data['response']:
            raise ValueError("초단기실황 API 응답 형식이 올바르지 않습니다.")
        
        items = ultra_srt_ncst_data["response"]["body"]["items"]["item"]
        current_weather = {}
        for item in items:
            current_weather[item["category"]] = item["obsrValue"]

        # 현재 날씨 정보
        temp = float(current_weather.get("T1H", "N/A"))
        humidity = int(current_weather.get("REH", "N/A"))
        rain = float(current_weather.get("RN1", "0"))
        wind_speed = float(current_weather.get("WSD", "N/A"))

        # 날씨 상태 결정
        pty = int(current_weather.get("PTY", "0"))
        weather_status = "맑음"
        if pty == 1:
            weather_status = "비"
        elif pty == 2:
            weather_status = "비/눈"
        elif pty == 3:
            weather_status = "눈"
        elif pty == 4:
            weather_status = "소나기"

        weather_info = f"현재 날씨는 {weather_status}입니다. "
        weather_info += f"기온은 {temp:.1f}도, 습도는 {humidity}%, "
        
        if rain > 0:
            weather_info += f"현재 강수량은 {rain:.1f}밀리미터 입니다."

        # 단기예보 데이터 가져오기
        vilage_fcst_url = f"{base_url}/getVilageFcst"
        vilage_fcst_params = {
            "serviceKey": service_key,
            "pageNo": "1",
            "numOfRows": "1000",
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": str(nx),
            "ny": str(ny),
        }

        vilage_fcst_response = requests.get(vilage_fcst_url, params=vilage_fcst_params)
        vilage_fcst_response.raise_for_status()
        logging.info(f"단기예보 API 응답: {vilage_fcst_response.text}")
        vilage_fcst_data = vilage_fcst_response.json()

        if vilage_fcst_data["response"]["header"]["resultCode"] == "00":
            items = vilage_fcst_data["response"]["body"]["items"]["item"]
            forecast = {}
            for item in items:
                if item["category"] not in forecast:
                    forecast[item["category"]] = []
                forecast[item["category"]].append({"fcstDate": item["fcstDate"], "fcstTime": item["fcstTime"], "fcstValue": item["fcstValue"]})

            today = now.strftime("%Y%m%d")
            tmx = max([float(item["fcstValue"]) for item in forecast.get("TMX", []) if item["fcstDate"] == today] or [float('-inf')])
            tmn = min([float(item["fcstValue"]) for item in forecast.get("TMN", []) if item["fcstDate"] == today] or [float('inf')])
            pop = max([int(item["fcstValue"]) for item in forecast.get("POP", []) if item["fcstDate"] == today] or [0])

            if tmx != float('-inf') and tmn != float('inf'):
                weather_info += f"오늘의 최고 기온은 {tmx:.1f}도, 최저 기온은 {tmn:.1f}도입니다. "
            elif tmx != float('-inf'):
                weather_info += f"오늘의 최고 기온은 {tmx:.1f}도입니다. "
            elif tmn != float('inf'):
                weather_info += f"오늘의 최저 기온은 {tmn:.1f}도입니다. "
            
            weather_info += f"강수 확률은 {pop}%입니다."
        else:
            weather_info += "최고/최저 기온과 강수 확률 정보는 현재 이용할 수 없습니다."

        return weather_info

    except requests.exceptions.RequestException as e:
        logging.error(f"날씨 정보 요청 오류: {str(e)}")
        return "날씨 정보를 가져오는 데 실패했습니다."
    except ValueError as e:
        logging.error(f"날씨 정보 처리 오류: {str(e)}")
        return "날씨 정보를 처리하는 데 실패했습니다."
    except Exception as e:
        logging.error(f"예상치 못한 오류 발생: {str(e)}", exc_info=True)
        return "날씨 정보를 가져오는 중 오류가 발생했습니다."


def convert_coord(lat, lon):
    # 위경도를 기상청 격자 좌표로 변환하는 함수
    RE = 6371.00877  # 지구 반경(km)
    GRID = 5.0  # 격자 간격(km)
    SLAT1 = 30.0  # 투영 위도1(degree)
    SLAT2 = 60.0  # 투영 위도2(degree)
    OLON = 126.0  # 기준점 경도(degree)
    OLAT = 38.0  # 기준점 위도(degree)
    XO = 43  # 기준점 X좌표(GRID)
    YO = 136  # 기준점 Y좌표(GRID)

    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / math.pow(ro, sn)

    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / math.pow(ra, sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    x = math.floor(ra * math.sin(theta) + XO + 0.5)
    y = math.floor(ro - ra * math.cos(theta) + YO + 0.5)

    return int(x), int(y)


def execute_command(command):
    global learning_mode, current_url, current_time
    logging.info(f"실행할 명령: {command}")

    if "학습 모드" in command:
        if "비활성화" in command or "종료" in command:
            learning_mode = False
            tts_wrapper("학습 모드가 비활성화되었습니다.")
        elif "활성화" in command or "시작" in command:
            learning_mode = True
            tts_wrapper("학습 모드가 활성화되었습니다.")
        return

    # 사이트 이름을 매핑하는 사전
    site_mapping = {"네이버": "naver", "유튜브": "youtube", "구글": "google"}

    if "볼륨" in command:
        if "키우기" in command or "올려" in command:
            adjust_volume(0.1)  # 10% 증가
        elif "줄이기" in command or "내려" in command:
            adjust_volume(-0.1)  # 10% 감소
        elif "음소거 해제" in command:
            adjust_volume(0)  # 현재 볼륨 유지
        elif "음소거" in command:
            adjust_volume(-1)  # 볼륨을 0으로 설정
    elif "유튜브" in command and ("재생" in command or "틀어줘" in command):
        query = command.split("유튜브")[1].split("재생" if "재생" in command else "틀어줘")[0].strip()
        search_and_play_youtube(query)
    elif "일시정지" in command or "일시 정지" in command:
        pause_youtube_playback()
    elif "다시 틀어줘" in command or "재개" in command:
        if current_url:
            threading.Thread(target=play_youtube_audio, args=(current_url, current_time)).start()
        else:
            resume_youtube_playback()
    elif "다음 곡" in command or "다음곡" in command:
        play_next_track()
    elif "이전 곡" in command or "이전곡" in command:
        play_previous_track()
    elif "재생 중지" in command or "정지" in command:
        stop_youtube_playback()
    elif "셔플" in command or "섞어줘" in command:
        shuffle_playlist()
    elif "열어 줘" in command:
        site = command.split("열어 줘")[0].strip()

        # 사이트 이름을 매핑된 값으로 변환
        site_key = site_mapping.get(site, site)

        open_website(
            f"https://www.{site_key}.com" if site_key else "https://www.google.com"
        )
        tts_wrapper("브라우저를 열었습니다.")
    elif "검색해 줘" in command:
        site = command.split("검색해 줘")[0].strip()
        open_website(f"https://www.google.com/search?q={site}")
        tts_wrapper(f"{site}에 대한 검색 결과입니다.")
    elif "타이머" in command:
        if "취소" in command or "끄기" in command or "중지" in command:
            cancel_timer()
        else:
            set_timer_from_command(command)
    elif "몇 시야" in command:
        current_time = get_current_time()
        response = f"현재 시간은 {current_time}입니다."
        tts_wrapper(response)
        logging.info(f"현재 시간 안내: {response}")
    elif "분 뒤에 컴퓨터 꺼 줘" in command or "분 후에 컴퓨터 꺼 줘" in command:
        set_shutdown_timer_from_command(command)
    elif "전원 꺼 줘" in command or "컴퓨터 꺼 줘" in command:
        tts_wrapper("컴퓨터를 종료합니다.")
        shutdown_computer()
    elif "날씨 어때" in command:
        try:
            lat, lon = get_current_location()
            logging.info(f"현재 위치: 위도 {lat}, 경도 {lon}")
            weather_info = get_weather_info(lat, lon)
            tts_wrapper(weather_info)
        except Exception as e:
            logging.error(f"날씨 정보 조회 중 오류 발생: {str(e)}")
            tts_wrapper("날씨 정보를 가져오는 데 실패했습니다.")
    elif "보내 줘" in command:
        partial_name = command.split("보내 줘")[0].strip()
        try:
            result = send_file(partial_name)
            logging.info(f"파일 공유 결과: {result}")
            tts_wrapper(result)
        except Exception as e:
            error_message = f"파일 공유 중 오류 발생: {str(e)}"
            logging.error(error_message, exc_info=True)
    else:
        response, entities, sentiment = ai_assistant.process_query(command)
        tts_wrapper(response)
        logging.info(f"인식된 개체: {entities}")
        logging.info(f"감성 분석 결과: {sentiment}")

        if learning_mode:
            tts_wrapper("응답이 적절했나요? '적절' 또는 '부적절'로 대답해주세요.")
            feedback = listen_for_feedback()

            if "부적절" in feedback.lower():
                tts_wrapper("새로운 응답을 말씀해 주세요.")
                new_response = listen_for_new_response()
                if new_response:
                    ai_assistant.learn_new_response(command, new_response)
                    tts_wrapper("새로운 응답을 학습했습니다. 감사합니다.")

                    # 강화학습 업데이트
                    ai_assistant.update_q_table(command, "say_sorry", -1, command)
                else:
                    tts_wrapper("새로운 응답을 학습하지 못했습니다. 죄송합니다.")
            else:
                tts_wrapper(
                    "감사합니다. 앞으로도 좋은 답변을 드리도록 노력하겠습니다."
                )

                # 강화학습 업데이트
                ai_assistant.update_q_table(command, "use_best_response", 1, command)


def listen_for_feedback():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        logging.info("피드백 대기 중...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)

    try:
        feedback = recognizer.recognize_google(audio, language="ko-KR")
        logging.info(f"인식된 피드백: {feedback}")
        return feedback
    except sr.UnknownValueError:
        logging.warning("피드백을 인식하지 못했습니다.")
        return "인식 실패"
    except sr.RequestError as e:
        logging.error(f"음성 인식 서비스 오류: {e}")
        return "오류 발생"


def listen_for_new_response():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        logging.info("새로운 응답 대기 중...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source, timeout=10, phrase_time_limit=10)

    try:
        new_response = recognizer.recognize_google(audio, language="ko-KR")
        logging.info(f"인식된 새로운 응답: {new_response}")
        return new_response
    except sr.UnknownValueError:
        tts_wrapper("죄송합니다. 응답을 이해하지 못했습니다. 다시 말씀해 주세요.")
        return listen_for_new_response()
    except sr.RequestError as e:
        logging.error(f"음성 인식 서비스 오류: {e}")
        tts_wrapper(
            "음성 인식 서비스에 문제가 발생했습니다. 나중에 다시 시도해 주세요."
        )
        return None


def home_assistant_command(domain, service, entity_id=None, additional_data=None):
    url = f"{get_home_assistant_url()}/api/services/{domain}/{service}"
    headers = {
        "Authorization": f"Bearer {get_home_assistant_token()}",
        "Content-Type": "application/json",
    }
    data = additional_data or {}
    if entity_id:
        data["entity_id"] = entity_id

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logging.error(f"Home Assistant 명령 실행 중 오류 발생: {e}")
        return False


def get_current_time():
    now = datetime.now()
    if now.hour < 12:
        am_pm = "오전"
        hour = now.hour
    else:
        am_pm = "오후"
        hour = now.hour - 12 if now.hour > 12 else 12
    return f"{am_pm} {hour}시 {now.minute}분"


def adjust_volume(change):
    try:
        current_volume = int(subprocess.check_output(["amixer", "sget", "Master"]).decode().split("[")[1].split("%")[0])
        new_volume = max(0, min(100, current_volume + int(change * 100)))
        subprocess.run(["amixer", "sset", "Master", f"{new_volume}%"])
        tts_wrapper(f"볼륨을 {new_volume}%로 조절했습니다.")
    except Exception as e:
        logging.error(f"볼륨 조절 실패: {str(e)}")
        tts_wrapper("볼륨 조절에 실패했습니다.")


def set_timer_from_command(command):
    try:
        minutes = int("".join(filter(str.isdigit, command)))
        set_timer(minutes)
    except ValueError:
        tts_wrapper("타이머 시간을 정확히 말씀해 주세요.")


def set_shutdown_timer_from_command(command):
    try:
        minutes = int("".join(filter(str.isdigit, command)))
        set_shutdown_timer(minutes)
    except ValueError:
        tts_wrapper("종료 시간을 정확히 말씀해 주세요.")


class VoiceCommandThread(QThread):
    command_signal = Signal(str)
    finished = Signal()
    start_listening_signal = Signal()
    stop_listening_signal = Signal()

    def __init__(self):
        super().__init__()
        self.recognizer = sr.Recognizer()
        self.vosk_recognizer = VoskRecognizer(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "vosk-model-small-ko-0.22"
            )
        )
        self.is_running = True
        self.is_listening = False
        self.is_processing = False
        self.is_tts_playing = False

    def run(self):
        while self.is_running:
            if self.is_listening and not self.is_processing and not self.is_tts_playing:
                try:
                    self.is_processing = True
                    with sr.Microphone() as source:
                        logging.info("명령을 기다리는 중...")
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                        audio = self.recognizer.listen(
                            source, timeout=5, phrase_time_limit=5
                        )
                    logging.info("음성 인식 중...")

                    # Vosk를 사용한 음성 인식
                    raw_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
                    vosk_result = self.vosk_recognizer.process_audio(raw_data)
                    if vosk_result:
                        command = vosk_result
                        logging.info(f"Vosk로 인식된 명령: {command}")
                        self.command_signal.emit(command)
                    else:
                        # Vosk로 인식되지 않은 경우, Google Speech Recognition 사용
                        command = self.recognizer.recognize_google(
                            audio, language="ko-KR"
                        )
                        logging.info(f"Google로 인식된 명령: {command}")
                        self.command_signal.emit(command)

                except sr.WaitTimeoutError:
                    logging.warning("음성 입력 대기 시간 초과")
                except sr.UnknownValueError:
                    logging.warning("음성을 인식할 수 없습니다.")
                except Exception as e:
                    logging.error(f"오류 발생: {str(e)}")
                finally:
                    self.is_processing = False
            time.sleep(0.1)

    def stop(self):
        self.is_running = False
        self.wait()

    def toggle_listening(self):
        if self.is_listening:
            self.stop_listening_signal.emit()
        else:
            self.start_listening_signal.emit()
        self.is_listening = not self.is_listening
        logging.info(f"음성 인식 {'활성화' if self.is_listening else '비활성화'}")


class VoiceRecognitionThread(QThread):
    result = Signal(str)
    listening_state_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.running = True
        self.selected_microphone = None
        self.microphone_index = None
        self.porcupine = None
        self.audio_stream = None
        self.access_key = use_api("picovoice_access_key")
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.keyword_path = os.path.join(
            current_dir, "아리야아_ko_raspberry-pi_v3_0_0.ppn"
        )
        self.model_path = os.path.join(current_dir, "porcupine_params_ko.pv")
        self.vosk_model = Model(os.path.join(current_dir, "vosk-model-ko-0.22"))
        self.recognizer = KaldiRecognizer(self.vosk_model, 16000)
        self.is_listening = False
        self.is_processing = False
        self.is_tts_playing = False

        # 마이크 초기화
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone(device_index=self.microphone_index)
        self.init_pipewire()
        self.init_audio_processing()

    def init_pipewire(self):
        try:
            # 기본 입력 장치 찾기
            result = subprocess.run(['pw-dump'], capture_output=True, text=True)
            nodes = json.loads(result.stdout)
            input_node = next((node for node in nodes if node.get('info', {}).get('props', {}).get('media.class') == 'Audio/Source'), None)
            
            if input_node:
                node_id = input_node['id']
                # 초기 볼륨을 높게 설정 (2.5 = 250%)
                subprocess.run(['pw-cli', 's', str(node_id), 'Props', '{"channelVolumes": [2.5, 2.5]}'])
                logging.info(f"PipeWire 입력 장치 볼륨 증가됨: {node_id}")
            
            # 노이즈 제거, AGC, 및 추가 필터 적용
            filter_chain = [
                {
                    "node.description": "Enhanced Audio Processing",
                    "media.name": "Enhanced Audio Processing",
                    "filter.graph": {
                        "nodes": [
                            {
                                "type": "filter",
                                "name": "noise_suppressor",
                                "plugin": "libspa-noise-remove",
                                "label": "Noise Suppressor",
                                "control": {
                                    "Suppression Level": 0.8  # 노이즈 제거 강화
                                }
                            },
                            {
                                "type": "filter",
                                "name": "agc",
                                "plugin": "libspa-audioconvert",
                                "label": "Audio Convert",
                                "control": {
                                    "volume": 1.0,
                                    "mute": false,
                                    "soft-volume": true,
                                    "auto-volume": true,
                                    "auto-volume-threshold": -30.0,  # 더 낮은 임계값
                                    "auto-volume-window": 300  # 더 빠른 반응
                                }
                            },
                            {
                                "type": "filter",
                                "name": "compressor",
                                "plugin": "libspa-audioconvert",
                                "label": "Audio Convert",
                                "control": {
                                    "compress": true,
                                    "compress-threshold": -24.0,
                                    "compress-ratio": 4.0,
                                    "compress-attack": 2.0,
                                    "compress-release": 200.0
                                }
                            }
                        ]
                    },
                    "capture.props": {
                        "node.name": "effect_input.enhanced_audio",
                        "node.passive": True
                    },
                    "playback.props": {
                        "node.name": "effect_output.enhanced_audio",
                        "media.class": "Audio/Source"
                    }
                }
            ]
            filter_json = json.dumps(filter_chain)
            subprocess.run(['pw-cli', 'create-filter', filter_json])
            logging.info("PipeWire 고급 오디오 처리 필터 적용됨")
            
            logging.info("PipeWire 설정 완료")
        except Exception as e:
            logging.error(f"PipeWire 설정 실패: {e}")

    def init_microphone(self):
        if self.selected_microphone:
            self.init_audio()
        else:
            logging.warning("선택된 마이크가 없습니다.")

    def init_audio(self):
        logging.info("PipeWire 오디오 초기화 중...")

        devices = sd.query_devices()
        input_devices = [d for d in devices if d['max_input_channels'] > 0]

        if not input_devices:
            logging.warning("입력 장치를 찾을 수 없습니다. 기본 장치를 사용합니다.")
            self.audio_stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype=np.int16,
                blocksize=512
            )
        else:
            device_index = None
            for i, device in enumerate(input_devices):
                if self.selected_microphone and self.selected_microphone in device['name']:
                    device_index = i
                    break

            if device_index is not None:
                self.audio_stream = sd.InputStream(
                    samplerate=16000,
                    channels=1,
                    dtype=np.int16,
                    blocksize=512,
                    device=device_index
                )
            else:
                logging.warning(f"선택한 마이크 '{self.selected_microphone}'를 찾을 수 없습니다. 기본 장치를 사용합니다.")
                self.audio_stream = sd.InputStream(
                    samplerate=16000,
                    channels=1,
                    dtype=np.int16,
                    blocksize=512
                )

        logging.info("PipeWire 오디오 초기화 완료")

    def get_pipewire_devices(self):
        try:
            result = subprocess.run(['pw-cli', 'list-objects'], capture_output=True, text=True)
            devices = []
            current_device = {}
            for line in result.stdout.split('\n'):
                if 'type PipeWire:Interface:Node' in line:
                    if current_device:
                        devices.append(current_device)
                    current_device = {}
                elif 'node.name =' in line:
                    current_device['name'] = line.split('=')[1].strip().strip('"')
                elif 'node.nick =' in line:
                    current_device['nick'] = line.split('=')[1].strip().strip('"')
                elif 'media.class =' in line and 'Audio/Source' in line:
                    current_device['is_input'] = True
            if current_device:
                devices.append(current_device)

            input_devices = [f"{d['nick']} ({d['name']})" for d in devices if d.get('is_input')]
            return input_devices
        except Exception as e:
            logging.error(f"PipeWire 장치 목록 가져오기 실패: {str(e)}")
            return []

    def set_microphone(self, microphone):
        if self.selected_microphone != microphone:
            self.selected_microphone = microphone
            self.microphone_index = self.get_microphone_index(microphone)
            if hasattr(self, "audio_stream") and self.audio_stream:
                self.audio_stream.close()
            self.init_audio()

    def get_microphone_index(self, microphone_name):
        import speech_recognition as sr
        for index, name in enumerate(sr.Microphone.list_microphone_names()):
            if microphone_name in name:
                return index
        return None

    def init_audio_processing(self):
        # 프리엠파시스 필터 계수
        self.preemphasis = 0.97
        
        # 노이즈 게이트 설정
        self.noise_gate_threshold = 300  # 조정 가능한 값
        
        # AGC 설정
        self.agc_target = 5000  # 목표 진폭
        self.agc_gain = 1.0
        self.agc_max_gain = 20.0
        self.agc_attack = 0.1
        self.agc_decay = 0.01

    def process_audio(self, audio_data):
        # int16에서 float32로 변환
        float_data = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        # 프리엠파시스 필터 적용
        emphasized_data = signal.lfilter([1, -self.preemphasis], [1], float_data)
        
        # 노이즈 게이트 적용
        gate_mask = np.abs(emphasized_data) > (self.noise_gate_threshold / 32768.0)
        gated_data = emphasized_data * gate_mask
        
        # AGC 적용
        max_amplitude = np.max(np.abs(gated_data))
        if max_amplitude > 0:
            target_gain = self.agc_target / (max_amplitude * 32768.0)
            if target_gain > self.agc_gain:
                self.agc_gain = min(self.agc_gain * (1 + self.agc_attack), target_gain, self.agc_max_gain)
            else:
                self.agc_gain = max(self.agc_gain * (1 - self.agc_decay), target_gain)
        
        amplified_data = gated_data * self.agc_gain
        
        # float32에서 int16으로 변환
        processed_data = np.clip(amplified_data * 32768.0, -32768, 32767).astype(np.int16)
        
        return processed_data.tobytes()

    def run(self):
        pa = pyaudio.PyAudio()
        audio_stream = pa.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.porcupine.frame_length,
            input_device_index=None,
        )

        try:
            while self.running:
                pcm = audio_stream.read(self.porcupine.frame_length, exception_on_overflow=False)
                
                # 오디오 신호 처리
                processed_pcm = self.process_audio(pcm)
                
                pcm_int16 = struct.unpack_from("h" * self.porcupine.frame_length, processed_pcm)

                keyword_index = self.porcupine.process(pcm_int16)

                if keyword_index >= 0:
                    logging.info("웨이크 워드 감지됨!")
                    self.wake_word_detected()
                    
                # Vosk를 사용한 음성 인식
                if self.is_listening and not self.is_processing and not self.is_tts_playing:
                    if self.recognizer.AcceptWaveform(processed_pcm):
                        result = json.loads(self.recognizer.Result())
                        if result.get("text", ""):
                            logging.info(f"인식된 텍스트: {result['text']}")
                            self.result.emit(result["text"])

        except Exception as e:
            logging.error(f"음성 인식 스레드 오류: {str(e)}")
        finally:
            audio_stream.stop_stream()
            audio_stream.close()
            pa.terminate()
            self.porcupine.delete()

    def init_porcupine(self):
        logging.info("Porcupine 초기화 중...")
        self.porcupine = pvporcupine.create(
            access_key=self.access_key,
            keyword_paths=[self.keyword_path],
            model_path=self.model_path,
            sensitivities=[1],
        )
        logging.info("Porcupine 초기화 완료")

    def handle_wake_word(self):
        logging.info("웨이크 워드 '아리야' 감지!")
        wake_responses = ["네?", "부르셨나요?"]
        response = random.choice(wake_responses)
        tts_wrapper(response)
        self.listening_state_changed.emit(True)
        voice_recognition_start()
        self.recognize_speech()
        idle()
        self.listening_state_changed.emit(False)

    def recognize_speech(self):
        try:
            voice_recognition_start()
            with self.microphone as source:
                logging.info("말씀해 주세요...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=5)

            text = self.recognizer.recognize_google(audio, language="ko-KR")
            logging.info(f"인식된 텍스트: {text}")
            self.result.emit(text)

        except sr.UnknownValueError:
            logging.warning("음성을 인식할 수 없습니다.")
            tts_wrapper("죄송합니다. 말씀을 이해하지 못했습니다.")
        except sr.RequestError as e:
            logging.error(f"음성 인식 서비스 오류: {e}")
            tts_wrapper("음성 인식 서비스에 문제가 발생했습니다.")
        except Exception as e:
            logging.error(f"음성 인식 중 오류 발생: {str(e)}", exc_info=True)
            tts_wrapper("죄송합니다. 오류가 발생했습니다.")
        finally:
            idle()

    def cleanup(self):
        logging.info("음성 인식 스레드 종료 중...")
        if hasattr(self, "audio_stream") and self.audio_stream:
            self.audio_stream.close()
        if self.porcupine is not None:
            self.porcupine.delete()
        logging.info("음성 인식 스레드 종료 완료")

    def get_voice_feedback(self):
        pass

    def stop(self):
        self.running = False
        self.wait()  # 스레드가 완전히 종료될 때까지 대기


# TTS 스레드
class TTSThread(QThread):
    def __init__(self):
        super().__init__()
        self.queue = Queue()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def run(self):
        while True:
            text = self.queue.get()
            if text is None:
                break
            self.loop.run_until_complete(text_to_speech(text))
            self.queue.task_done()

    def speak(self, text):
        self.queue.put(text)


# 명령 실행 스레드

class CommandExecutionThread(QThread):
    def __init__(self):
        super().__init__()
        self.queue = Queue()

    def run(self):
        while True:
            command = self.queue.get()
            if command is None:
                break
            execute_command(command)
            self.queue.task_done()

    def execute(self, command):
        self.queue.put(command)
