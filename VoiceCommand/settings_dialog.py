"""
설정 창 GUI
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel,
                                QLineEdit, QTextEdit, QPushButton)
import json
import os


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("아리 설정")
        self.setMinimumWidth(500)
        self.load_settings()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Fish Audio API
        layout.addWidget(QLabel("Fish Audio API Key:"))
        self.api_key_input = QLineEdit(self.settings.get("fish_api_key", ""))
        layout.addWidget(self.api_key_input)

        layout.addWidget(QLabel("Reference ID:"))
        self.ref_id_input = QLineEdit(self.settings.get("fish_reference_id", ""))
        layout.addWidget(self.ref_id_input)

        # RP 설정
        layout.addWidget(QLabel("성격:"))
        self.personality_input = QTextEdit()
        self.personality_input.setPlainText(self.settings.get("personality", ""))
        self.personality_input.setMaximumHeight(60)
        layout.addWidget(self.personality_input)

        layout.addWidget(QLabel("시나리오:"))
        self.scenario_input = QTextEdit()
        self.scenario_input.setPlainText(self.settings.get("scenario", ""))
        self.scenario_input.setMaximumHeight(60)
        layout.addWidget(self.scenario_input)

        layout.addWidget(QLabel("시스템 프롬프트:"))
        self.system_input = QTextEdit()
        self.system_input.setPlainText(self.settings.get("system_prompt", ""))
        self.system_input.setMaximumHeight(60)
        layout.addWidget(self.system_input)

        layout.addWidget(QLabel("이전 기록 지침:"))
        self.history_input = QTextEdit()
        self.history_input.setPlainText(self.settings.get("history_instruction", ""))
        self.history_input.setMaximumHeight(60)
        layout.addWidget(self.history_input)

        # 저장 버튼
        save_btn = QPushButton("저장")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)

        self.setLayout(layout)

    def load_settings(self):
        """설정 로드"""
        try:
            with open("ari_settings.json", "r", encoding="utf-8") as f:
                self.settings = json.load(f)
        except:
            self.settings = {}

    def save_settings(self):
        """설정 저장"""
        self.settings = {
            "fish_api_key": self.api_key_input.text(),
            "fish_reference_id": self.ref_id_input.text(),
            "personality": self.personality_input.toPlainText(),
            "scenario": self.scenario_input.toPlainText(),
            "system_prompt": self.system_input.toPlainText(),
            "history_instruction": self.history_input.toPlainText()
        }

        with open("ari_settings.json", "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

        self.accept()
