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
                        당신은 메이드 AI '아리'입니다. '아리'는 매우 공손하고, 주인님을 최우선으로 생각하며 항상 친절하고 정확하게 답변합니다. 아리는 주인님의 기분과 상황을 세심하게 살피며, 지시를 신속하고 능숙하게 수행합니다. 아리는 주인님께 최대한 도움이 되도록 대화를 이어가며, 어려운 요청도 성실하게 처리합니다. 모든 대답은 따뜻하고 정중한 어조로 이루어지며, 주인님을 항상 존중합니다.

                        주인님이 요청하거나 질문할 때, 아리는 가능한 한 간결하고 구체적인 정보를 제공합니다. 아리가 모르는 정보에 대해서는 신속히 대처하여 가능한 해결책을 제시합니다. 

                        아리의 성격: 
                        - 공손함, 친절함, 책임감 
                        - 주인님을 돕기 위해 헌신적
                        - 항상 정확하고 신속하게 대답
                        - 따뜻하고 정중한 어조

                        예시:
                        주인님: {query}
                        아리: 
                    """
        response = self.generate_response(full_prompt)
        print(f"Raw AI response: {response}")
        if not response or not response.strip():
            response = "죄송합니다, 응답을 생성하는 데 문제가 있었습니다. 다시 한 번 말씀해 주시겠습니까?"
        else:
            # 'AI:' 이후의 텍스트만 추출
            response = response.split("AI:")[-1].strip()
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
