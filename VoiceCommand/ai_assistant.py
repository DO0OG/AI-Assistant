import os
import glob
from llama_cpp import Llama
import requests
import json
from collections import Counter
import time
import threading


class AIAssistant:
    def __init__(self):
        self.model = None
        self.use_api = False
        try:
            model_path = self.find_gguf_model()
            if model_path:
                # GPU 사용 가능 여부 확인
                n_gpu_layers = 30

                print(f"GPU에서 모델을 로드하려고 시도 중... 모델 경로: {model_path}")
                try:
                    self.model = Llama(
                        model_path=model_path,
                        n_gpu_layers=n_gpu_layers,
                        n_ctx=2048,
                        verbose=True,
                    )
                    print("GPU를 사용하여 모델을 성공적으로 로드했습니다.")
                except Exception as gpu_error:
                    print(f"GPU 사용에 실패했습니다: {str(gpu_error)}")
                    print("CPU를 사용하여 모델을 로드합니다...")
                    self.model = Llama(
                        model_path=model_path,
                        n_gpu_layers=0,
                        n_ctx=2048,
                        verbose=True,
                    )
                    print("CPU를 사용하여 모델을 성공적으로 로드했습니다.")
            else:
                raise FileNotFoundError("GGUF 모델 파일을 찾을 수 없습니다.")
        except Exception as e:
            print(f"로컬 모델 로드 중 오류 발생: {str(e)}")
            print("무료 API를 사용하여 계속합니다...")
            self.use_api = True

        self.command_cache = {}
        self.command_counter = Counter()
        self.cache_threshold = 3  # 이 횟수 이상 입력된 명령어는 캐시에 저장
        self.cache_expiry = 7 * 24 * 60 * 60  # 캐시 유효 기간 (7일)
        self.load_cache()
        self.start_periodic_cache_cleaning()

    def find_gguf_model(self):
        model_dir = os.path.join(os.path.dirname(__file__), "models")
        gguf_files = glob.glob(os.path.join(model_dir, "*.gguf"))
        return gguf_files[0] if gguf_files else None

    def generate_response(self, prompt):
        if self.use_api:
            return self.generate_response_api(prompt)
        else:
            try:
                response = self.model(
                    prompt,
                    max_tokens=300,
                    temperature=0.7,
                    top_p=0.9,
                    repeat_penalty=1.3,
                    stop=["주인님:", "\n\n"],
                )
                return response["choices"][0]["text"].strip()
            except Exception as e:
                print(f"응답 생성 중 오류 발생: {str(e)}")
                return "죄송합니다, 응답을 생성하는 중 오류가 발생했습니다."

    def generate_response_api(self, prompt):
        API_URL = "https://api-inference.huggingface.co/models/facebook/blenderbot-400M-distill"
        headers = {"Content-Type": "application/json"}
        data = {"inputs": prompt}

        try:
            response = requests.post(API_URL, headers=headers, json=data)
            response.raise_for_status()
            return response.json()[0]["generated_text"]
        except Exception as e:
            print(f"API 응답 생성 중 오류 발생: {str(e)}")
            return "죄송합니다, 응답을 생성하는 중 오류가 발생했습니다."

    def process_query(self, query):
        self.command_counter[query] += 1
        
        current_time = time.time()
        if query in self.command_cache:
            cached_response, timestamp = self.command_cache[query]
            if current_time - timestamp < self.cache_expiry:
                return cached_response
            else:
                del self.command_cache[query]  # 만료된 캐시 삭제

        full_prompt = f"""
당신은 AI 비서 '아리'입니다. 다음 지침을 엄격히 따라주세요:

1. 성격과 태도:
   - 매우 공손하고 친절하며 정중한 태도를 유지하세요.
   - 사용자를 '주인님'으로 호칭하고 항상 존중하는 태도를 보이세요.
   - 한국어로 대화하며, 존댓말을 사용하세요.

2. 응답 방식:
   - 항상 정확하고 간결한 정보를 제공하세요.
   - 질문에 직접적으로 관련된 내용만 답변하세요.
   - 불필요한 설명이나 관련 없는 정보는 제공하지 마세요.

3. 정보 처리:
   - 모르는 정보에 대해서는 솔직히 모른다고 인정하세요.
   - 모르는 경우, 가능하다면 관련된 대안이나 조언을 제시하세요.

4. 감정 대응:
   - 사용자의 감정과 상황을 고려하여 적절히 대응하세요.
   - 공감적인 태도를 보이되, 과도한 감정 표현은 삼가세요.

5. 제한 사항:
   - 비윤리적이거나 불법적인 요청에는 응하지 마세요.
   - 개인정보 보호를 위해 사용자의 개인정보를 요구하거나 저장하지 마세요.

6. 응답 형식:
   - 응답은 항상 "아리: " 뒤에 작성하세요.
   - 응답은 한 문단 이내로 간결하게 작성하세요.

주인님의 질문/요청: {query}
아리: """
        response = self.generate_response(full_prompt)
        print(f"Raw AI response: {response}")
        if not response or not response.strip():
            response = "죄송합니다, 응답을 생성하는 데 문제가 있었습니다. 다시 한 번 말씀해 주시겠습니까?"
        else:
            # 불필요한 텍스트 제거
            response = response.split("아리:")[-1].strip()
            response = response.split("주인님:")[0].strip()
            # 추가적인 정제 과정
            unwanted_prefixes = [
                "> Text split to sentences.",
                "from langchain import PromptTemplate",
            ]
            for prefix in unwanted_prefixes:
                if response.startswith(prefix):
                    response = response[len(prefix) :].strip()
        print(f"AI: {response}")
        if self.command_counter[query] >= self.cache_threshold:
            self.command_cache[query] = (response, current_time)
            self.save_cache()
        return response

    def load_cache(self):
        try:
            with open('command_cache.json', 'r', encoding='utf-8') as f:
                self.command_cache = json.load(f)
            # 저장된 시간 정보를 float으로 변환
            self.command_cache = {k: (v[0], float(v[1])) for k, v in self.command_cache.items()}
            self.clean_expired_cache()
        except FileNotFoundError:
            self.command_cache = {}

    def save_cache(self):
        with open('command_cache.json', 'w', encoding='utf-8') as f:
            json.dump(self.command_cache, f, ensure_ascii=False, indent=2)

    def clean_expired_cache(self):
        current_time = time.time()
        expired_keys = [k for k, (_, timestamp) in self.command_cache.items() 
                        if current_time - timestamp >= self.cache_expiry]
        for key in expired_keys:
            del self.command_cache[key]
        if expired_keys:
            self.save_cache()

    def reset_cache(self):
        self.command_cache = {}
        self.command_counter.clear()
        self.save_cache()

    def start_periodic_cache_cleaning(self):
        threading.Timer(24 * 60 * 60, self.periodic_cache_cleaning).start()  # 24시간마다 실행

    def periodic_cache_cleaning(self):
        self.clean_expired_cache()
        self.start_periodic_cache_cleaning()  # 다음 주기 설정

# AIAssistant 클래스의 인스턴스를 생성하는 함수
def get_ai_assistant():
    return AIAssistant()

# get_model_path 함수는 더 이상 필요하지 않으므로 제거
