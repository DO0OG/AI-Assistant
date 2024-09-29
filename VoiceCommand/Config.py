import json
import requests

SERVER_URL = "http://dogs.kro.kr:5000"  # 실제 서버 URL로 변경해야 함

# 설정 파일에서 API 키 로드
def load_config():
    response = requests.get(f"{SERVER_URL}/get_encrypted_keys")
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception("Failed to load encrypted keys from server")

def use_api(key_name, api_url, params={}):
    encrypted_key = config[key_name]
    response = requests.post(f"{SERVER_URL}/decrypt_and_use", json={
        'encrypted_key': encrypted_key,
        'api_url': api_url,
        'params': params
    })
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception("Failed to use API")

config = load_config()
