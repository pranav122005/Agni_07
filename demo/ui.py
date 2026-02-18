import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QTextEdit, QPushButton, QLabel
)
from PyQt6.QtCore import Qt
import pygame
import time

from helpline_ai import get_ai_response
from tts_engine import text_to_speech

class HelplineUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Road Emergency Helpline")
        self.setGeometry(400, 200, 600, 400)

        layout = QVBoxLayout()

        self.label = QLabel("Describe your emergency:")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText(
            "Example: My car engine stopped suddenly on the highway..."
        )

        self.response_box = QTextEdit()
        self.response_box.setReadOnly(True)

        self.send_btn = QPushButton("Get Help")
        self.send_btn.clicked.connect(self.process_query)

        layout.addWidget(self.label)
        layout.addWidget(self.input_box)
        layout.addWidget(self.send_btn)
        layout.addWidget(QLabel("Helpline Response:"))
        layout.addWidget(self.response_box)

        self.setLayout(layout)

    def process_query(self):
        user_text = self.input_box.toPlainText().strip()
        if not user_text:
            return

        self.response_box.setText("Processing emergency request...")
        QApplication.processEvents()

        ai_response = get_ai_response(user_text)
        self.response_box.setText(ai_response)

        # Generate voice
        text_to_speech(ai_response)

        # Play audio
        self.play_audio()

    def play_audio(self):
        pygame.mixer.init()
        pygame.mixer.music.load("tts.wav")
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HelplineUI()
    window.show()
    sys.exit(app.exec())
