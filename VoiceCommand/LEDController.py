import RPi.GPIO as GPIO
import threading
import time
import logging


class LEDController:
    def __init__(self, pin=23):
        self.pin = pin
        self.is_running = True
        self.current_state = "ON"
        self.setup_gpio()
        self.thread = threading.Thread(target=self.run)
        self.thread.start()
        logging.info(f"LED 컨트롤러 초기화 완료 (PIN: {self.pin})")

    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        self.pwm = GPIO.PWM(self.pin, 100)
        self.pwm.start(100)
        logging.info("GPIO 설정 완료")

    def run(self):
        while self.is_running:
            if self.current_state == "ON":
                self.pwm.ChangeDutyCycle(100)
            elif self.current_state == "TTS":
                self.pulse(0.1)
            elif self.current_state == "VOICE_RECOGNITION":
                self.pulse(0.01)
            time.sleep(0.1)

    def pulse(self, speed):
        while self.current_state in ["TTS", "VOICE_RECOGNITION"]:
            for duty in range(0, 101, 5):
                if self.current_state not in ["TTS", "VOICE_RECOGNITION"]:
                    break
                self.pwm.ChangeDutyCycle(duty)
                time.sleep(speed)
            for duty in range(100, -1, -5):
                if self.current_state not in ["TTS", "VOICE_RECOGNITION"]:
                    break
                self.pwm.ChangeDutyCycle(duty)
                time.sleep(speed)

    def set_state(self, state):
        self.current_state = state
        logging.info(f"LED 상태 변경: {state}")

    def cleanup(self):
        self.is_running = False
        self.thread.join()
        self.pwm.stop()
        GPIO.cleanup(self.pin)
        logging.info("LED 컨트롤러 정리 완료")


led_controller = None


def get_led_controller():
    global led_controller
    if led_controller is None:
        led_controller = LEDController()
    return led_controller


def voice_recognition_start():
    get_led_controller().set_state("VOICE_RECOGNITION")


def tts_start():
    get_led_controller().set_state("TTS")


def idle():
    get_led_controller().set_state("ON")


def cleanup():
    global led_controller
    if led_controller:
        led_controller.cleanup()
        led_controller = None
