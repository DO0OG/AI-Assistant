import json

# 설정 파일에서 API 키 로드
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

config = load_config()
