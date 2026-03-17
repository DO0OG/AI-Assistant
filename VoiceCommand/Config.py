"""
간단한 로컬 설정 관리
"""
import json
import logging


def use_api(key_name):
    """로컬 설정에서 API 키 읽기"""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get(key_name)
    except:
        return None
