"""
RAAM - Road Assistance & Alert Monitor
Driver Emergency Dashboard Application
Uses PyQt6 for UI, Groq for AI responses, and TTS with Autumn voice
"""

import sys
import os
import json
import threading
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QLineEdit, QScrollArea,
    QFrame, QGridLayout, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation,
    QEasingCurve, QSize, QRect, pyqtProperty
)
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QPainter, QLinearGradient,
    QRadialGradient, QBrush, QPen, QPixmap, QIcon,
    QFontDatabase, QPainterPath
)

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("Groq not installed. Run: pip install groq")

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

# ─── THEME CONSTANTS ───────────────────────────────────────────────────────────
COLORS = {
    "bg_deep":        "#0A0F1E",
    "bg_panel":       "#0D1529",
    "bg_card":        "#111D35",
    "accent_amber":   "#F5A623",
    "accent_red":     "#E84545",
    "accent_teal":    "#00D4AA",
    "accent_blue":    "#4A9EFF",
    "text_primary":   "#E8EDF5",
    "text_secondary": "#7B8BAE",
    "text_muted":     "#3D4F6E",
    "border":         "#1E2D4A",
    "border_active":  "#2A4080",
    "glow_amber":     "rgba(245,166,35,0.15)",
    "glow_teal":      "rgba(0,212,170,0.15)",
    "glow_red":       "rgba(232,69,69,0.2)",
}

SYSTEM_PROMPT = """You are RAAM — Road Assistance & Alert Monitor. You are an AI co-pilot designed to assist drivers during emergencies, stressful situations, or when they need guidance on the road.

Your personality:
- Calm, warm, and reassuring at all times
- Speak in a natural, conversational tone — like a trusted friend in the passenger seat
- Use simple, clear language — no jargon
- Be concise but thorough — drivers need quick answers
- Always prioritize safety first
- Acknowledge emotions — if someone is scared or stressed, validate that first

Your capabilities:
- Guide drivers through emergency situations (accidents, breakdowns, medical emergencies)
- Provide step-by-step instructions for common roadside problems
- Help navigate stressful driving situations
- Offer calming reassurance during anxiety-inducing situations
- Advise when to call emergency services (911)

Always start with the most critical safety information. Keep responses short when urgency is high. Use gentle, supportive language. Never panic — your calm is contagious."""


# ─── GROQ AI THREAD ────────────────────────────────────────────────────────────
class GroqThread(QThread):
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    chunk_ready = pyqtSignal(str)

    def __init__(self, client, messages):
        super().__init__()
        self.client = client
        self.messages = messages

    def run(self):
        try:
            stream = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=self.messages,
                temperature=0.7,
                max_tokens=500,
                stream=True,
            )
            full_response = ""
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                full_response += delta
                self.chunk_ready.emit(delta)
            self.response_ready.emit(full_response)
        except Exception as e:
            self.error_occurred.emit(str(e))


# ─── TTS THREAD ────────────────────────────────────────────────────────────────
class TTSThread(QThread):
    finished = pyqtSignal()

    def __init__(self, text, client=None):
        super().__init__()
        self.text = text
        self.client = client

    def run(self):
        try:
            # Try Groq TTS with Autumn voice first
            if self.client:
                try:
                    response = self.client.audio.speech.create(
                        model="canopylabs/orpheus-v1-english",
                        voice="autumn",
                        input=self.text[:500],
                        response_format="wav",
                    )
                    import tempfile, os as _os
                    audio_path = _os.path.join(tempfile.gettempdir(), "raam_tts.wav")
                    with open(audio_path, "wb") as f:
                        f.write(response.read())

                    if PYGAME_AVAILABLE:
                        pygame.mixer.quit()
                        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
                        sound = pygame.mixer.Sound(audio_path)
                        sound.play()
                        while pygame.mixer.get_busy():
                            time.sleep(0.05)
                        pygame.mixer.quit()
                    self.finished.emit()
                    return
                except Exception as e:
                    print(f"Groq TTS error: {e}")

            # Fallback to pyttsx3
            if TTS_AVAILABLE:
                engine = pyttsx3.init()
                voices = engine.getProperty('voices')
                # Try to find a female voice for Autumn-like quality
                for voice in voices:
                    if 'female' in voice.name.lower() or 'zira' in voice.name.lower() or 'hazel' in voice.name.lower():
                        engine.setProperty('voice', voice.id)
                        break
                engine.setProperty('rate', 165)
                engine.setProperty('volume', 0.9)
                engine.say(self.text)
                engine.runAndWait()
        except Exception as e:
            print(f"TTS error: {e}")
        self.finished.emit()


# ─── PULSE ANIMATION WIDGET ────────────────────────────────────────────────────
class PulseWidget(QWidget):
    def __init__(self, color="#F5A623", parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self._opacity = 0.0
        self._radius = 0.0
        self.setFixedSize(60, 60)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._phase = 0.0
        self._anim_timer.start(30)

    def _tick(self):
        self._phase = (self._phase + 0.05) % (2 * 3.14159)
        import math
        self._opacity = (math.sin(self._phase) + 1) / 2
        self._radius = 15 + 10 * (math.sin(self._phase) + 1) / 2
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2

        # Outer pulse
        glow = QColor(self.color)
        glow.setAlphaF(self._opacity * 0.3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        r = int(self._radius)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # Inner dot
        core = QColor(self.color)
        core.setAlphaF(0.9)
        p.setBrush(QBrush(core))
        p.drawEllipse(cx - 8, cy - 8, 16, 16)


# ─── EMERGENCY BUTTON ──────────────────────────────────────────────────────────
class EmergencyButton(QPushButton):
    def __init__(self, icon_text, label, color, parent=None):
        super().__init__(parent)
        self.icon_text = icon_text
        self.label = label
        self.base_color = color
        self.setFixedSize(130, 100)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False

        self.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.04);
                border: 1px solid {COLORS['border']};
                border-radius: 16px;
                color: {COLORS['text_primary']};
                font-family: 'Segoe UI';
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.08);
                border: 1px solid {color};
            }}
            QPushButton:pressed {{
                background: rgba(255,255,255,0.12);
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        icon_lbl = QLabel(icon_text)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 24))
        icon_lbl.setStyleSheet("background: transparent; border: none;")

        text_lbl = QLabel(label)
        text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        text_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; border: none;")

        layout.addWidget(icon_lbl)
        layout.addWidget(text_lbl)


# ─── STATUS BAR WIDGET ─────────────────────────────────────────────────────────
class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)

        # Logo
        logo = QLabel("◈ RAAM")
        logo.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        logo.setStyleSheet(f"color: {COLORS['accent_amber']}; letter-spacing: 4px;")

        # Status indicators
        self.status_label = QLabel("● ACTIVE")
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setStyleSheet(f"color: {COLORS['accent_teal']};")

        self.time_label = QLabel()
        self.time_label.setFont(QFont("Segoe UI", 10))
        self.time_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

        timer = QTimer(self)
        timer.timeout.connect(self._update_time)
        timer.start(1000)
        self._update_time()

        ai_badge = QLabel("AI COPILOT")
        ai_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        ai_badge.setStyleSheet(f"""
            color: {COLORS['accent_amber']};
            background: rgba(245,166,35,0.1);
            border: 1px solid rgba(245,166,35,0.3);
            border-radius: 4px;
            padding: 2px 8px;
            letter-spacing: 2px;
        """)

        layout.addWidget(logo)
        layout.addSpacing(12)
        layout.addWidget(self.status_label)
        layout.addStretch()
        layout.addWidget(ai_badge)
        layout.addSpacing(16)
        layout.addWidget(self.time_label)

        self.setStyleSheet(f"""
            background: {COLORS['bg_panel']};
            border-bottom: 1px solid {COLORS['border']};
        """)

    def _update_time(self):
        self.time_label.setText(datetime.now().strftime("%H:%M  %d %b %Y"))

    def set_status(self, text, color):
        self.status_label.setText(f"● {text}")
        self.status_label.setStyleSheet(f"color: {color};")


# ─── CHAT BUBBLE ───────────────────────────────────────────────────────────────
class ChatBubble(QWidget):
    def __init__(self, text, is_user=False, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        if is_user:
            layout.addStretch()

        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setFont(QFont("Segoe UI", 11))
        bubble.setMaximumWidth(480)
        bubble.setContentsMargins(14, 10, 14, 10)

        if is_user:
            bubble.setStyleSheet(f"""
                background: rgba(74,158,255,0.15);
                border: 1px solid rgba(74,158,255,0.3);
                border-radius: 16px 4px 16px 16px;
                color: {COLORS['text_primary']};
            """)
        else:
            bubble.setStyleSheet(f"""
                background: rgba(0,212,170,0.08);
                border: 1px solid rgba(0,212,170,0.2);
                border-radius: 4px 16px 16px 16px;
                color: {COLORS['text_primary']};
            """)

        layout.addWidget(bubble)

        if not is_user:
            layout.addStretch()


# ─── MAIN WINDOW ───────────────────────────────────────────────────────────────
class RAAMDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RAAM — Road Assistance & Alert Monitor")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 800)

        # Load API key
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.client = None
        self.conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.tts_enabled = True
        self.is_speaking = False

        if GROQ_AVAILABLE and self.api_key:
            try:
                self.client = Groq(api_key=self.api_key)
            except Exception as e:
                print(f"Groq init error: {e}")

        self._setup_ui()
        self._apply_global_style()

        # Welcome message
        QTimer.singleShot(800, self._send_welcome)

    def _apply_global_style(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {COLORS['bg_deep']};
                color: {COLORS['text_primary']};
                font-family: 'Segoe UI', sans-serif;
            }}
            QScrollBar:vertical {{
                background: {COLORS['bg_panel']};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border_active']};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{ height: 0px; }}
        """)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Status Bar
        self.status_bar = StatusBar()
        root.addWidget(self.status_bar)

        # Main Content
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ── LEFT SIDEBAR ──
        sidebar = self._build_sidebar()
        content_layout.addWidget(sidebar)

        # ── MAIN CHAT AREA ──
        chat_area = self._build_chat_area()
        content_layout.addWidget(chat_area, stretch=1)

        # ── RIGHT PANEL ──
        right_panel = self._build_right_panel()
        content_layout.addWidget(right_panel)

        root.addWidget(content, stretch=1)

    def _build_sidebar(self):
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"""
            background: {COLORS['bg_panel']};
            border-right: 1px solid {COLORS['border']};
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(12)

        # Pulse + RAAM status
        pulse_row = QHBoxLayout()
        self.pulse = PulseWidget(COLORS['accent_teal'])
        pulse_label = QLabel("RAAM\nActive")
        pulse_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        pulse_label.setStyleSheet(f"color: {COLORS['text_primary']};")
        pulse_row.addWidget(self.pulse)
        pulse_row.addWidget(pulse_label)
        pulse_row.addStretch()
        layout.addLayout(pulse_row)

        layout.addWidget(self._divider())

        # Emergency Scenarios
        scenarios_label = QLabel("QUICK SCENARIOS")
        scenarios_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        scenarios_label.setStyleSheet(f"color: {COLORS['text_muted']}; letter-spacing: 2px;")
        layout.addWidget(scenarios_label)

        scenarios = [
            ("🚨", "Emergency SOS", "I need immediate help — emergency!"),
            ("💥", "Accident", "I've been in a car accident."),
            ("🔧", "Breakdown", "My car broke down on the road."),
            ("🩺", "Medical", "I'm feeling unwell while driving."),
            ("🌧️", "Bad Weather", "Weather conditions are dangerous."),
            ("⛽", "Out of Fuel", "I've run out of fuel."),
            ("🔒", "Locked Out", "I'm locked out of my car."),
            ("🛞", "Flat Tire", "I have a flat tire."),
        ]

        for icon, label, message in scenarios:
            btn = self._scenario_button(icon, label, message)
            layout.addWidget(btn)

        layout.addStretch()

        # TTS Toggle
        self.tts_btn = QPushButton("🔊  Voice Response ON")
        self.tts_btn.setCheckable(True)
        self.tts_btn.setChecked(True)
        self.tts_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tts_btn.setFont(QFont("Segoe UI", 9))
        self.tts_btn.clicked.connect(self._toggle_tts)
        self.tts_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,212,170,0.1);
                border: 1px solid rgba(0,212,170,0.3);
                border-radius: 8px;
                color: {COLORS['accent_teal']};
                padding: 8px;
            }}
            QPushButton:checked {{
                background: rgba(0,212,170,0.1);
            }}
            QPushButton:hover {{
                background: rgba(0,212,170,0.18);
            }}
        """)
        layout.addWidget(self.tts_btn)

        # Clear Chat
        clear_btn = QPushButton("🗑  Clear Chat")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setFont(QFont("Segoe UI", 9))
        clear_btn.clicked.connect(self._clear_chat)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.04);
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                color: {COLORS['text_secondary']};
                padding: 8px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.08);
                color: {COLORS['text_primary']};
            }}
        """)
        layout.addWidget(clear_btn)

        return sidebar

    def _scenario_button(self, icon, label, message):
        btn = QPushButton(f"{icon}  {label}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont("Segoe UI", 9))
        btn.setFixedHeight(34)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.03);
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                color: {COLORS['text_secondary']};
                text-align: left;
                padding-left: 8px;
            }}
            QPushButton:hover {{
                background: rgba(245,166,35,0.08);
                border: 1px solid rgba(245,166,35,0.3);
                color: {COLORS['accent_amber']};
            }}
        """)
        btn.clicked.connect(lambda: self._quick_message(message))
        return btn

    def _build_chat_area(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Chat header
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(f"""
            background: {COLORS['bg_card']};
            border-bottom: 1px solid {COLORS['border']};
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 0, 24, 0)

        chat_title = QLabel("RAAM Assistant")
        chat_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        chat_title.setStyleSheet(f"color: {COLORS['text_primary']};")

        self.thinking_label = QLabel("")
        self.thinking_label.setFont(QFont("Segoe UI", 10))
        self.thinking_label.setStyleSheet(f"color: {COLORS['accent_teal']};")

        h_layout.addWidget(chat_title)
        h_layout.addSpacing(16)
        h_layout.addWidget(self.thinking_label)
        h_layout.addStretch()

        # API status
        api_status_text = "✓ Groq Connected" if (self.client and self.api_key) else "⚠ No API Key"
        api_status_color = COLORS['accent_teal'] if (self.client and self.api_key) else COLORS['accent_amber']
        api_status = QLabel(api_status_text)
        api_status.setFont(QFont("Segoe UI", 9))
        api_status.setStyleSheet(f"color: {api_status_color};")
        h_layout.addWidget(api_status)

        layout.addWidget(header)

        # Scroll area for messages
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(f"background: {COLORS['bg_deep']};")

        self.messages_widget = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(16, 16, 16, 16)
        self.messages_layout.setSpacing(8)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_widget)
        layout.addWidget(self.scroll_area, stretch=1)

        # Input area
        input_area = self._build_input_area()
        layout.addWidget(input_area)

        return container

    def _build_input_area(self):
        area = QWidget()
        area.setFixedHeight(80)
        area.setStyleSheet(f"""
            background: {COLORS['bg_panel']};
            border-top: 1px solid {COLORS['border']};
        """)

        layout = QHBoxLayout(area)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Describe your situation... RAAM is here to help")
        self.input_field.setFont(QFont("Segoe UI", 12))
        self.input_field.setFixedHeight(46)
        self.input_field.returnPressed.connect(self._send_message)
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
                color: {COLORS['text_primary']};
                padding: 0 16px;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['accent_amber']};
                background: {COLORS['bg_card']};
            }}
            QLineEdit::placeholder {{
                color: {COLORS['text_muted']};
            }}
        """)

        self.send_btn = QPushButton("Send ↗")
        self.send_btn.setFixedSize(100, 46)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.send_btn.clicked.connect(self._send_message)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent_amber']};
                border: none;
                border-radius: 12px;
                color: #0A0F1E;
            }}
            QPushButton:hover {{
                background: #F7BC50;
            }}
            QPushButton:pressed {{
                background: #D4901A;
            }}
            QPushButton:disabled {{
                background: {COLORS['text_muted']};
                color: {COLORS['border']};
            }}
        """)

        layout.addWidget(self.input_field)
        layout.addWidget(self.send_btn)

        return area

    def _build_right_panel(self):
        panel = QWidget()
        panel.setFixedWidth(240)
        panel.setStyleSheet(f"""
            background: {COLORS['bg_panel']};
            border-left: 1px solid {COLORS['border']};
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(14)

        # Emergency contacts
        ec_label = QLabel("EMERGENCY CONTACTS")
        ec_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        ec_label.setStyleSheet(f"color: {COLORS['text_muted']}; letter-spacing: 2px;")
        layout.addWidget(ec_label)

        contacts = [
            ("🚑", "Ambulance", "911"),
            ("🚒", "Fire Dept", "911"),
            ("🚔", "Police", "911"),
            ("🛣️", "Road Help", "1-800-AAA"),
            ("💊", "Poison Control", "1-800-222-1222"),
        ]

        for icon, name, number in contacts:
            contact_widget = self._contact_card(icon, name, number)
            layout.addWidget(contact_widget)

        layout.addWidget(self._divider())

        # Safety tips
        tips_label = QLabel("SAFETY REMINDERS")
        tips_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        tips_label.setStyleSheet(f"color: {COLORS['text_muted']}; letter-spacing: 2px;")
        layout.addWidget(tips_label)

        tips = [
            "Stay in your vehicle if safe",
            "Turn on hazard lights",
            "Move to shoulder if possible",
            "Keep calm & breathe slowly",
            "Stay on the line with 911",
        ]

        for tip in tips:
            tip_lbl = QLabel(f"· {tip}")
            tip_lbl.setWordWrap(True)
            tip_lbl.setFont(QFont("Segoe UI", 9))
            tip_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 2px 0;")
            layout.addWidget(tip_lbl)

        layout.addStretch()

        # Big SOS button
        sos_btn = QPushButton("🆘  SOS EMERGENCY")
        sos_btn.setFixedHeight(52)
        sos_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sos_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        sos_btn.clicked.connect(lambda: self._quick_message("EMERGENCY! I need immediate help right now!"))
        sos_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(232,69,69,0.15);
                border: 2px solid {COLORS['accent_red']};
                border-radius: 12px;
                color: {COLORS['accent_red']};
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: rgba(232,69,69,0.25);
            }}
            QPushButton:pressed {{
                background: rgba(232,69,69,0.35);
            }}
        """)
        layout.addWidget(sos_btn)

        return panel

    def _contact_card(self, icon, name, number):
        card = QWidget()
        card.setFixedHeight(42)
        card.setStyleSheet(f"""
            background: rgba(255,255,255,0.03);
            border: 1px solid {COLORS['border']};
            border-radius: 8px;
        """)
        row = QHBoxLayout(card)
        row.setContentsMargins(10, 0, 10, 0)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 14))
        icon_lbl.setStyleSheet("background: transparent; border: none;")

        name_lbl = QLabel(name)
        name_lbl.setFont(QFont("Segoe UI", 9))
        name_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; border: none;")

        num_lbl = QLabel(number)
        num_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        num_lbl.setStyleSheet(f"color: {COLORS['accent_teal']}; background: transparent; border: none;")

        row.addWidget(icon_lbl)
        row.addWidget(name_lbl)
        row.addStretch()
        row.addWidget(num_lbl)

        return card

    def _divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {COLORS['border']}; background: {COLORS['border']}; border: none; max-height: 1px;")
        return line

    # ─── MESSAGE HANDLING ──────────────────────────────────────────────────────
    def _add_message(self, text, is_user=False):
        bubble = ChatBubble(text, is_user)
        # Insert before the stretch at the end
        count = self.messages_layout.count()
        self.messages_layout.insertWidget(count - 1, bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _send_welcome(self):
        welcome = "Hello! I'm RAAM, your Road Assistance & Alert Monitor. I'm here with you, calm and ready to help. Whether it's a breakdown, an accident, or just a stressful drive — tell me what's happening and we'll handle it together. 🧡"
        self._add_message(welcome, is_user=False)
        if self.tts_enabled:
            self._speak(welcome)

    def _quick_message(self, message):
        self.input_field.setText(message)
        self._send_message()

    def _send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()
        self._add_message(text, is_user=True)
        self.conversation_history.append({"role": "user", "content": text})

        self.send_btn.setEnabled(False)
        self.input_field.setEnabled(False)
        self.thinking_label.setText("RAAM is thinking...")
        self.status_bar.set_status("THINKING", COLORS['accent_amber'])

        if self.client:
            self._current_response = ""
            self._response_bubble = None

            self.groq_thread = GroqThread(self.client, self.conversation_history.copy())
            self.groq_thread.chunk_ready.connect(self._on_chunk)
            self.groq_thread.response_ready.connect(self._on_response_complete)
            self.groq_thread.error_occurred.connect(self._on_error)
            self.groq_thread.start()
        else:
            # Demo fallback
            demo_response = "I hear you, and I want you to know — you're not alone right now. Please make sure you're in a safe location. If this is a life-threatening emergency, please call 911 immediately. I'm here to guide you through this step by step. Can you tell me more about what's happening?"
            self._add_message(demo_response, is_user=False)
            self._finish_response(demo_response)

    def _on_chunk(self, chunk):
        self._current_response += chunk
        if self._response_bubble is None:
            self._response_bubble = ChatBubble(self._current_response, is_user=False)
            count = self.messages_layout.count()
            self.messages_layout.insertWidget(count - 1, self._response_bubble)
        else:
            # Update the label text
            label = self._response_bubble.findChild(QLabel)
            if label:
                label.setText(self._current_response)
        QTimer.singleShot(20, self._scroll_to_bottom)

    def _on_response_complete(self, full_text):
        self.conversation_history.append({"role": "assistant", "content": full_text})
        self._finish_response(full_text)

    def _on_error(self, error):
        msg = f"I'm having a little trouble connecting right now. Please call 911 if this is an emergency. Error: {error}"
        self._add_message(msg, is_user=False)
        self._finish_response(msg)

    def _finish_response(self, text):
        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)
        self.thinking_label.setText("")
        self.status_bar.set_status("ACTIVE", COLORS['accent_teal'])

        if self.tts_enabled and not self.is_speaking:
            self._speak(text)

    def _speak(self, text):
        self.is_speaking = True
        self.tts_thread = TTSThread(text, self.client)
        self.tts_thread.finished.connect(self._on_speak_done)
        self.tts_thread.start()

    def _on_speak_done(self):
        self.is_speaking = False

    def _toggle_tts(self, checked):
        self.tts_enabled = checked
        if checked:
            self.tts_btn.setText("🔊  Voice Response ON")
        else:
            self.tts_btn.setText("🔇  Voice Response OFF")

    def _clear_chat(self):
        # Remove all bubbles (except the stretch)
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]
        QTimer.singleShot(300, self._send_welcome)


# ─── ENTRY POINT ───────────────────────────────────────────────────────────────
def main():
    if not os.path.exists(".env"):
        # Create sample .env if not exists
        with open(".env", "w") as f:
            f.write("# Add your Groq API key here\nGROQ_API_KEY=your_groq_api_key_here\n")
        print("Created .env file — please add your GROQ_API_KEY")

    app = QApplication(sys.argv)
    app.setApplicationName("RAAM")
    app.setApplicationVersion("1.0")

    # High DPI
    app.setStyle("Fusion")

    window = RAAMDashboard()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()