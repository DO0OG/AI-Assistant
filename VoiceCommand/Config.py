import os
import json

# MeCab 경로 지정 (윈도우 전용)
if os.name == "nt":
    mecab_path = r"C:\Program Files\MeCab\bin"
    if mecab_path not in os.environ["PATH"]:
        os.environ["PATH"] = mecab_path + os.pathsep + os.environ["PATH"]

    # MeCab 사전 경로 지정
    dicdir = r"C:\Program Files\MeCab\dic\ipadic"
    os.environ["MECAB_DICDIR"] = dicdir

# 설정 파일에서 API 키 로드
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

config = load_config()
