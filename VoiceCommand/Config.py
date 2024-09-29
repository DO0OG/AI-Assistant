import os
import json
import requests

# MeCab 경로 지정 (윈도우 전용)
if os.name == "nt":
    mecab_path = r"C:\Program Files\MeCab\bin"
    if mecab_path not in os.environ["PATH"]:
        os.environ["PATH"] = mecab_path + os.pathsep + os.environ["PATH"]

    # MeCab 사전 경로 지정
    dicdir = r"C:\Program Files\MeCab\dic\ipadic"
    os.environ["MECAB_DICDIR"] = dicdir

SERVER_URL = "http://dogs.kro.kr:5000"  # 실제 서버 IP와 포트로 변경해야 함

def load_config():
    try:
        response = requests.get(f"{SERVER_URL}/get_encrypted_keys")
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"서버에서 키를 가져오는데 실패했습니다. 상태 코드: {response.status_code}")
    except requests.RequestException as e:
        print(f"서버 연결 오류: {e}")
        # 서버 연결 실패 시 로컬 config.json 파일 사용
        print("로컬 config.json 파일을 사용합니다.")
        with open("config.json", "r") as f:
            return json.load(f)

def use_api(key_name, api_url=None, params={}):
    try:
        encrypted_key = config[key_name]
        response = requests.post(f"{SERVER_URL}/decrypt_and_use", json={
            'encrypted_key': encrypted_key,
            'api_url': api_url,
            'params': params
        })
        if response.status_code == 200:
            if api_url:
                return response.json()
            else:
                return response.text  # 복호화된 키를 문자열로 반환
        else:
            raise Exception(f"API 사용 실패. 상태 코드: {response.status_code}")
    except Exception as e:
        print(f"API 사용 중 오류 발생: {e}")
        return None

config = load_config()
