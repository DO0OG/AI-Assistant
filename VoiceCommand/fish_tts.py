"""
Fish Audio TTS API
"""
import requests
import logging
import tempfile
import os
import pygame


class FishTTS:
    def __init__(self, api_key="", reference_id=""):
        self.api_key = api_key
        self.reference_id = reference_id
        self.base_url = "https://api.fish.audio/v1/tts"

        # pygame mixer 초기화
        try:
            pygame.mixer.init()
            logging.info("pygame mixer 초기화 완료")
        except Exception as e:
            logging.error(f"pygame mixer 초기화 실패: {e}")

    def speak(self, text):
        """텍스트를 음성으로 변환 후 재생"""
        if not self.api_key:
            logging.warning("Fish Audio API 키가 설정되지 않았습니다.")
            return False

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            data = {
                "text": text,
                "reference_id": self.reference_id,
                "format": "mp3"
            }

            response = requests.post(self.base_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()

            # 임시 MP3 파일로 저장
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tmp_path = tmp_file.name
                tmp_file.write(response.content)

            # pygame으로 재생
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()

            # 재생 완료까지 대기
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)

            # 임시 파일 삭제
            try:
                os.unlink(tmp_path)
            except:
                pass

            return True

        except Exception as e:
            logging.error(f"Fish TTS 오류: {e}")
            return False
