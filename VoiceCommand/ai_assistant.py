import os
from llama_cpp import Llama


class AIAssistant:
    def __init__(self, model_path):
        try:
            self.model = Llama(
                model_path=model_path,
                n_gpu_layers=50,  # GPU 레이어 수 (조정 가능)
                n_ctx=2048,  # 컨텍스트 길이
            )
            print(f"모델 로드 완료: {model_path}")
        except Exception as e:
            print(f"모델 로드 중 오류 발생: {str(e)}")
            raise

    def generate_response(self, prompt):
        response = self.model(
            prompt,
            max_tokens=300,
            temperature=0.7,
            top_p=0.9,
            repeat_penalty=1.3,
            stop=["user:", "\n\n"],
        )
        return response["choices"][0]["text"].strip()

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
                    아리: 
                """
        response = self.generate_response(full_prompt)
        print(f"Raw AI response: {response}")
        if not response or not response.strip():
            response = "죄송합니다, 응답을 생성하는 데 문제가 있었습니다. 다시 한 번 말씀해 주시겠습니까?"
        else:
            # '아리:' 이후의 텍스트만 추출하고 '주인님:' 이전에서 멈춤
            response = response.split("아리:")[-1].split("주인님:")[0].strip()
        print(f"AI: {response}")
        return response


# 모델 경로 설정 (절대 경로 사용)
MODEL_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "models",
        "DarkIdol-Llama-3.1-8B-Instruct-1.2-Uncensored.Q4_K_M.gguf",
    )
)


# AIAssistant 클래스의 인스턴스를 생성하는 함수
def get_ai_assistant():
    return AIAssistant(MODEL_PATH)
