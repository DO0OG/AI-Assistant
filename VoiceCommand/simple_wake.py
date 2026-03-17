"""
간단한 음성 트리거 (계정 불필요)
"""
import speech_recognition as sr
import logging


class SimpleWakeWord:
    def __init__(self, wake_words=["아리야", "시작"]):
        self.wake_words = wake_words
        self.recognizer = sr.Recognizer()

    def listen_for_wake_word(self):
        """웨이크워드 대기"""
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=2)

            text = self.recognizer.recognize_google(audio, language="ko-KR")
            logging.debug(f"들은 내용: {text}")

            # 웨이크워드 확인
            for wake_word in self.wake_words:
                if wake_word in text:
                    return True
            return False

        except sr.WaitTimeoutError:
            return False
        except sr.UnknownValueError:
            return False
        except Exception as e:
            logging.debug(f"음성 감지 오류: {e}")
            return False
