from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
import joblib
import os

class AIAssistant:
    def __init__(self):
        self.model = self.load_or_create_model()
        self.vectorizer = CountVectorizer()
        self.classes = ['greeting', 'farewell', 'unknown']
        self.responses = {
            'greeting': '안녕하세요! 무엇을 도와드릴까요?',
            'farewell': '안녕히 가세요!',
            'unknown': '죄송합니다, 잘 이해하지 못했어요.'
        }
        self.training_data = []
        self.last_query = None
        self.last_intent = None

    def load_or_create_model(self):
        if os.path.exists('ai_model.joblib'):
            return joblib.load('ai_model.joblib')
        else:
            return MultinomialNB()

    def save_model(self):
        joblib.dump(self.model, 'ai_model.joblib')

    def train(self, text, intent):
        self.training_data.append((text, intent))
        X = self.vectorizer.fit_transform([t for t, _ in self.training_data])
        y = [i for _, i in self.training_data]
        self.model.fit(X, y)
        self.save_model()

    def predict(self, text):
        X = self.vectorizer.transform([text])
        intent = self.model.predict(X)[0]
        self.last_query = text
        self.last_intent = intent
        return self.responses.get(intent, self.responses['unknown'])

    def process_query(self, query):
        response = self.predict(query)
        return response

    def learn_from_interaction(self, is_correct):
        if self.last_query and self.last_intent:
            if is_correct:
                self.train(self.last_query, self.last_intent)
                print(f"학습 완료: '{self.last_query}' -> {self.last_intent}")
            else:
                print(f"오답 처리: '{self.last_query}' -> {self.last_intent}")
        self.last_query = None
        self.last_intent = None

# AIAssistant 클래스의 인스턴스를 생성하는 함수
def get_ai_assistant():
    return AIAssistant()
