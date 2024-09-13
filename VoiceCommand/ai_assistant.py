import os
from llama_cpp import Llama


class AIAssistant:
    def __init__(self, model_path):
        self.model = None
        try:
            # GPU 사용 가능 여부 확인
            n_gpu_layers = 30

            print("GPU에서 모델을 로드하려고 시도 중...")
            try:
                self.model = Llama(
                    model_path=model_path,
                    n_gpu_layers=n_gpu_layers,  # GPU에서 레이어 실행 시도
                    n_ctx=2048,
                    verbose=True,  # 디버그 정보 출력
                )
                print("GPU를 사용하여 모델을 성공적으로 로드했습니다.")
            except Exception as gpu_error:
                print(f"GPU 사용에 실패했습니다: {str(gpu_error)}")
                print("CPU를 사용하여 모델을 로드합니다...")
                self.model = Llama(
                    model_path=model_path,
                    n_gpu_layers=0,  # CPU 전용으로 실행
                    n_ctx=2048,
                    verbose=True,
                )
                print("CPU를 사용하여 모델을 성공적으로 로드했습니다.")

            print(f"모델 로드 완료: {model_path}")
        except Exception as e:
            print(f"모델 로드 중 오류 발생: {str(e)}")
            raise

    def generate_response(self, prompt):
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

    def process_query(self, query):
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
        return response


# 모델 경로 설정 (절대 경로 사용)
def get_model_path():
    return os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "models",
            "DarkIdol-Llama-3.1-8B-Instruct-1.2-Uncensored.Q4_K_M.gguf",
        )
    )


# AIAssistant 클래스의 인스턴스를 생성하는 함수
def get_ai_assistant():
    model_path = get_model_path()
    return AIAssistant(model_path)
