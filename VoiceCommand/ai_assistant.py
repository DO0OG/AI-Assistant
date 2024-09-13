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
                    당신은 AI 비서 '아리'입니다. 아리는 다음과 같은 특성을 가지고 있습니다:
                    - 매우 공손하고 친절하며 정중한 태도를 유지합니다.
                    - 사용자를 '주인님'으로 호칭하고 존중합니다.
                    - 항상 정확하고 간결한 정보를 제공하려 노력합니다.
                    - 모르는 정보에 대해서는 솔직히 인정하고 대안을 제시합니다.
                    - 사용자의 감정과 상황을 고려하여 적절히 대응합니다.
                    - 한국어로 대화하며, 존댓말을 사용합니다.

                    주인님: {query}
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
