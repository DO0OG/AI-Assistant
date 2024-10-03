import torch
import torch.nn as nn
from transformers import BertTokenizer, BertModel
import tensorflow as tf
import numpy as np
import nltk
import spacy
from collections import defaultdict
import json
import os
import logging

Sequential = tf.keras.Sequential
LSTM = tf.keras.layers.LSTM
Dense = tf.keras.layers.Dense

class AdvancedAIAssistant(nn.Module):
    def __init__(self, bert_model_name='bert-base-uncased', lstm_units=128, output_size=100):
        super(AdvancedAIAssistant, self).__init__()
        self.bert = BertModel.from_pretrained(bert_model_name)
        self.lstm = nn.LSTM(input_size=self.bert.config.hidden_size, hidden_size=lstm_units, batch_first=True)
        self.fc = nn.Linear(lstm_units, output_size)
        self.tokenizer = BertTokenizer.from_pretrained(bert_model_name)
        
        # NLP 도구
        nltk.download('punkt')
        nltk.download('averaged_perceptron_tagger')
        nltk.download('maxent_ne_chunker')
        nltk.download('words')
        self.nlp = spacy.load("ko_core_news_sm")
        
        # Q-테이블 초기화
        self.q_table = defaultdict(lambda: {'use_best_response': 0, 'say_sorry': 0})
        
        # 응답 저장소
        self.responses = []
        
        self.save_counter = 0
        self.save_interval = 1  # 1번 학습할 때마다 저장

    def forward(self, input_ids, attention_mask):
        bert_output = self.bert(input_ids=input_ids, attention_mask=attention_mask)[0]
        lstm_output, _ = self.lstm(bert_output)
        return self.fc(lstm_output[:, -1, :])

    def process_query(self, query):
        # NLP 처리
        doc = self.nlp(query)
        entities = [(ent.text, ent.label_) for ent in doc.ents]
        sentiment = doc.sentiment
        
        # BERT 인코딩
        inputs = self.tokenizer(query, return_tensors="pt", padding=True, truncation=True)
        
        # 모델 추론
        with torch.no_grad():
            output = self(inputs['input_ids'], inputs['attention_mask'])
        
        # 응답 선택
        if not self.responses:  # self.responses가 비어 있는 경우
            response = "죄송합니다. 아직 학습된 응답이 없습니다."
        else:
            similarities = torch.cosine_similarity(output, torch.stack([r['vector'] for r in self.responses]))
            best_response_idx = similarities.argmax().item()
            best_response = self.responses[best_response_idx]['text']
        
        # 강화학습을 통한 응답 선택
        state = query
        action = self.choose_action(state)
        
        if action == 'use_best_response' and self.responses:
            response = best_response
        else:
            response = "죄송합니다. 적절한 응답을 찾지 못했습니다."
        
        return response, entities, sentiment

    def learn_new_response(self, query, response):
        inputs = self.tokenizer(query, return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            vector = self(inputs['input_ids'], inputs['attention_mask'])
        self.responses.append({'text': response, 'vector': vector.squeeze()})
        
        # 학습 후 저장 카운터 증가 및 저장
        self.save_counter += 1
        if self.save_counter >= self.save_interval:
            self.save_model()
            self.save_counter = 0

    def choose_action(self, state):
        if np.random.random() < 0.1:  # 탐험
            return np.random.choice(['use_best_response', 'say_sorry'])
        else:  # 활용
            if state not in self.q_table or not self.q_table[state]:
                return 'use_best_response'  # 기본 액션
            return max(self.q_table[state], key=self.q_table[state].get)

    def update_q_table(self, state, action, reward, next_state):
        if state not in self.q_table:
            self.q_table[state] = {'use_best_response': 0, 'say_sorry': 0}
        
        if next_state not in self.q_table:
            self.q_table[next_state] = {'use_best_response': 0, 'say_sorry': 0}
        
        old_q_value = self.q_table[state][action]
        next_max_q = max(self.q_table[next_state].values())
        
        new_q_value = old_q_value + 0.1 * (reward + 0.9 * next_max_q - old_q_value)
        self.q_table[state][action] = new_q_value

    def save_model(self, folder_name='saved_model'):
        try:
            current_dir = os.getcwd()
            save_path = os.path.join(current_dir, folder_name)
            os.makedirs(save_path, exist_ok=True)
            
            logging.info(f"모델 저장 시작: {save_path}")
            
            # 가중치 저장
            weights_path = os.path.join(save_path, 'model_weights.pth')
            torch.save(self.state_dict(), weights_path)
            logging.info(f"가중치 저장 완료: {weights_path}")
            
            # 토크나이저 저장
            self.tokenizer.save_pretrained(save_path)
            logging.info(f"토크나이저 저장 완료: {save_path}")
            
            # 응답 저장
            responses_path = os.path.join(save_path, 'responses.json')
            with open(responses_path, 'w', encoding='utf-8') as f:
                json.dump([{'text': r['text'], 'vector': r['vector'].tolist()} for r in self.responses], f, ensure_ascii=False, indent=2)
            logging.info(f"응답 저장 완료: {responses_path}")
            
            # Q-테이블 저장
            q_table_path = os.path.join(save_path, 'q_table.json')
            with open(q_table_path, 'w', encoding='utf-8') as f:
                json.dump({k: dict(v) for k, v in self.q_table.items()}, f, ensure_ascii=False, indent=2)
            logging.info(f"Q-테이블 저장 완료: {q_table_path}")
            
            logging.info(f"모델 저장 완료: {save_path}")
        except Exception as e:
            logging.error(f"모델 저장 중 오류 발생: {str(e)}", exc_info=True)

    @classmethod
    def load_model(cls, path, bert_model_name='bert-base-uncased', lstm_units=128, output_size=100):
        model = cls(bert_model_name, lstm_units, output_size)
        
        # 가중치 로드
        model.load_state_dict(torch.load(os.path.join(path, 'model_weights.pth')))
        
        # 토크나이저 로드
        model.tokenizer = BertTokenizer.from_pretrained(path)
        
        # 응답 로드
        with open(os.path.join(path, 'responses.json'), 'r', encoding='utf-8') as f:
            model.responses = [{'text': r['text'], 'vector': torch.tensor(r['vector'])} for r in json.load(f)]
        
        # Q-테이블 로드
        with open(os.path.join(path, 'q_table.json'), 'r', encoding='utf-8') as f:
            model.q_table = defaultdict(lambda: {'use_best_response': 0, 'say_sorry': 0}, json.load(f))
        
        return model

def get_ai_assistant():
    return AdvancedAIAssistant()
