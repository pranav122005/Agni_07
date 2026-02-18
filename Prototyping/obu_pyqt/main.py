import sys
import socket
import json
import time
import geocoder
import speech_recognition as sr

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QTextEdit,
    QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette


# ================= CONFIG =================
ESP32_IP = "192.168.137.222"   # RSU IP
PORT = 5005
VEHICLE_ID = "CAR_01"
STATUS_LISTEN_PORT = 5009      # Receives help-on-the-way updates from relay

# ================= COLORS =================
BG_DEEP    = "#0A0F1E"
BG_PANEL   = "#0D1529"
BG_CARD    = "#111D35"
ACCENT_RED = "#E84545"
ACCENT_TEAL = "#00D4AA"
ACCENT_AMBER = "#F5A623"
ACCENT_BLUE = "#4A9EFF"
TEXT_PRIMARY = "#E8EDF5"
TEXT_SECONDARY = "#7B8BAE"
TEXT_MUTED  = "#3D4F6E"
BORDER_CLR = "#1E2D4A"


# ================= STATUS LISTENER THREAD =================
class StatusListenerThread(QThread):
    """Listens for status updates from relay server (e.g. Car2 ACK, ETA)."""
    status_received = pyqtSignal(dict)

    def __init__(self, port):
        super().__init__()
        self.port = port
        self._running = True

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        sock.bind(("0.0.0.0", self.port))

        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
                pkt = json.loads(data.decode())
                self.status_received.emit(pkt)
            except socket.timeout:
                continue
            except Exception:
                continue

    def stop(self):
        self._running = False


# ================= VOICE RECORDER THREAD =================
class VoiceRecorderThread(QThread):
    """Background thread that records from the microphone and transcribes."""

    transcription_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                self.status_update.emit("🎙️ Adjusting for ambient noise...")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)

                self.status_update.emit("🎙️ Listening... Speak now!")
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)

                if self._stop_flag:
                    return

                self.status_update.emit("⏳ Transcribing...")
                text = recognizer.recognize_google(audio)
                self.transcription_ready.emit(text)

        except sr.WaitTimeoutError:
            self.error_occurred.emit("No speech detected. Please try again.")
        except sr.UnknownValueError:
            self.error_occurred.emit("Could not understand audio. Please speak clearly.")
        except sr.RequestError as e:
            self.error_occurred.emit(f"Speech service error: {e}")
        except OSError as e:
            self.error_occurred.emit(f"Microphone error: {e}")
        except Exception as e:
            self.error_occurred.emit(f"Recording error: {e}")


class CarOBU(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("🚗 Car 1 — On-Board Unit")
        self.setFixedSize(500, 600)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recorder_thread = None

        self.init_ui()
        self.start_status_listener()

    # ---------------- UI ----------------
    def init_ui(self):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_DEEP};
                color: {TEXT_PRIMARY};
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── HEADER ──
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_PANEL};
                border-bottom: 1px solid {BORDER_CLR};
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("◈ CAR 1 — OBU")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT_AMBER}; letter-spacing: 2px;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        self.header_status = QLabel("● READY")
        self.header_status.setFont(QFont("Segoe UI", 9))
        self.header_status.setStyleSheet(f"color: {ACCENT_TEAL};")
        h_layout.addWidget(self.header_status)

        layout.addWidget(header)

        # ── BODY ──
        body = QFrame()
        body.setStyleSheet(f"background-color: {BG_DEEP};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        body_layout.setSpacing(16)

        # Issue input card
        input_card = QFrame()
        input_card.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_CLR};
                border-radius: 12px;
            }}
        """)
        ic_layout = QVBoxLayout(input_card)
        ic_layout.setContentsMargins(16, 12, 16, 12)
        ic_layout.setSpacing(8)

        input_title = QLabel("DESCRIBE VEHICLE PROBLEM")
        input_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        input_title.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")
        ic_layout.addWidget(input_title)

        self.issue_input = QTextEdit()
        self.issue_input.setPlaceholderText("Type your issue or use voice recording...")
        self.issue_input.setFixedHeight(100)
        self.issue_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {BG_PANEL};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_CLR};
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
            }}
            QTextEdit:focus {{
                border-color: {ACCENT_AMBER};
            }}
        """)
        ic_layout.addWidget(self.issue_input)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.record_button = QPushButton("🎤 Record Voice")
        self.record_button.setFixedHeight(42)
        self.record_button.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.record_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_TEAL};
                color: {BG_DEEP};
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{ background-color: #00E8BB; }}
        """)
        self.record_button.clicked.connect(self.toggle_recording)
        btn_row.addWidget(self.record_button)

        self.send_button = QPushButton("🚨 Send Emergency")
        self.send_button.setFixedHeight(42)
        self.send_button.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.send_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_RED};
                color: white;
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{ background-color: #F05555; }}
        """)
        self.send_button.clicked.connect(self.send_emergency)
        btn_row.addWidget(self.send_button)

        ic_layout.addLayout(btn_row)
        body_layout.addWidget(input_card)

        # Status card
        self.status_card = QFrame()
        self.status_card.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_CLR};
                border-radius: 12px;
            }}
        """)
        sc_layout = QVBoxLayout(self.status_card)
        sc_layout.setContentsMargins(16, 12, 16, 12)
        sc_layout.setSpacing(6)

        st_title = QLabel("STATUS")
        st_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        st_title.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")
        sc_layout.addWidget(st_title)

        self.status_label = QLabel("Ready to send emergency alert")
        self.status_label.setFont(QFont("Segoe UI", 11))
        self.status_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self.status_label.setWordWrap(True)
        sc_layout.addWidget(self.status_label)

        body_layout.addWidget(self.status_card)

        # Help status card (hidden until help confirmed)
        self.help_card = QFrame()
        self.help_card.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 2px solid {ACCENT_TEAL};
                border-radius: 12px;
            }}
        """)
        hc_layout = QVBoxLayout(self.help_card)
        hc_layout.setContentsMargins(16, 12, 16, 12)
        hc_layout.setSpacing(6)

        help_title = QLabel("🆘 HELP STATUS")
        help_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        help_title.setStyleSheet(f"color: {ACCENT_TEAL}; letter-spacing: 2px;")
        hc_layout.addWidget(help_title)

        self.help_label = QLabel("")
        self.help_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.help_label.setStyleSheet(f"color: {ACCENT_AMBER};")
        self.help_label.setWordWrap(True)
        hc_layout.addWidget(self.help_label)

        self.help_eta = QLabel("")
        self.help_eta.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.help_eta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.help_eta.setStyleSheet(f"color: {ACCENT_TEAL};")
        hc_layout.addWidget(self.help_eta)

        self.help_detail = QLabel("")
        self.help_detail.setFont(QFont("Segoe UI", 10))
        self.help_detail.setStyleSheet(f"color: {TEXT_SECONDARY};")
        hc_layout.addWidget(self.help_detail)

        self.help_card.hide()
        body_layout.addWidget(self.help_card)

        body_layout.addStretch()
        layout.addWidget(body, 1)

    # ---------------- STATUS LISTENER ----------------
    def start_status_listener(self):
        self.status_listener = StatusListenerThread(STATUS_LISTEN_PORT)
        self.status_listener.status_received.connect(self.on_status_received)
        self.status_listener.start()

    def on_status_received(self, packet):
        if packet.get("type") == "HELP_COMING":
            helper_id = packet.get("helper_id", "Unknown")
            eta = packet.get("eta_minutes", "?")
            dist = packet.get("distance_km", "?")

            self.help_card.show()
            self.help_label.setText(f"🚙 {helper_id} is coming to help!")
            self.help_eta.setText(f"ETA: {eta} minutes")
            self.help_detail.setText(f"Distance: {dist} km away")

            self.header_status.setText("● HELP ON THE WAY")
            self.header_status.setStyleSheet(f"color: {ACCENT_TEAL};")

    # ---------------- VOICE RECORDING ----------------
    def toggle_recording(self):
        if self.recorder_thread and self.recorder_thread.isRunning():
            self.recorder_thread.stop()
            self.recorder_thread.quit()
            self.record_button.setText("🎤 Record Voice")
            self.record_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ACCENT_TEAL};
                    color: {BG_DEEP};
                    border: none;
                    border-radius: 10px;
                }}
                QPushButton:hover {{ background-color: #00E8BB; }}
            """)
            self.status_label.setText("Recording stopped")
            self.status_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        else:
            self.recorder_thread = VoiceRecorderThread()
            self.recorder_thread.transcription_ready.connect(self.on_transcription)
            self.recorder_thread.error_occurred.connect(self.on_recording_error)
            self.recorder_thread.status_update.connect(self.on_voice_status)
            self.recorder_thread.finished.connect(self.on_recording_finished)
            self.recorder_thread.start()

            self.record_button.setText("⏹ Stop Recording")
            self.record_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ACCENT_RED};
                    color: white;
                    border: none;
                    border-radius: 10px;
                }}
                QPushButton:hover {{ background-color: #F05555; }}
            """)

    def on_transcription(self, text):
        current = self.issue_input.toPlainText()
        if current:
            self.issue_input.setPlainText(current + " " + text)
        else:
            self.issue_input.setPlainText(text)
        self.status_label.setText("Voice transcribed ✅")
        self.status_label.setStyleSheet(f"color: {ACCENT_TEAL};")

    def on_recording_error(self, msg):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {ACCENT_RED};")

    def on_voice_status(self, msg):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {ACCENT_AMBER};")

    def on_recording_finished(self):
        self.record_button.setText("🎤 Record Voice")
        self.record_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_TEAL};
                color: {BG_DEEP};
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{ background-color: #00E8BB; }}
        """)

    # ---------------- GPS ----------------
    def get_location(self):
        g = geocoder.ip('me')
        if g.ok:
            return g.latlng
        return [0, 0]

    # ---------------- CLASSIFIER ----------------
    def classify_issue(self, text):
        text = text.lower()
        if "tire" in text:
            return "Flat Tire"
        elif "battery" in text or "not starting" in text:
            return "Battery Failure"
        elif "smoke" in text or "engine" in text:
            return "Engine Problem"
        elif "accident" in text or "crash" in text or "collision" in text:
            return "Accident"
        elif "fire" in text:
            return "Vehicle Fire"
        else:
            return "General Breakdown"

    # ---------------- SEND FUNCTION ----------------
    def send_emergency(self):
        issue_text = self.issue_input.toPlainText().strip()

        if not issue_text:
            QMessageBox.warning(self, "Error", "Please describe the problem.")
            return

        lat, lon = self.get_location()
        classified_issue = self.classify_issue(issue_text)

        packet = {
            "vehicle_id": VEHICLE_ID,
            "issue": classified_issue,
            "raw_description": issue_text,
            "latitude": lat,
            "longitude": lon,
            "timestamp": time.strftime("%H:%M:%S"),
            "hop_trace": [VEHICLE_ID]
        }

        message = json.dumps(packet)

        try:
            print("Sending packet to:", ESP32_IP, PORT)
            print("Packet Data:", packet)

            self.socket.sendto(message.encode(), (ESP32_IP, PORT))

            self.status_label.setText("Emergency Sent Successfully 🚨")
            self.status_label.setStyleSheet(f"color: {ACCENT_TEAL};")

            self.header_status.setText("● EMERGENCY SENT")
            self.header_status.setStyleSheet(f"color: {ACCENT_RED};")

        except Exception as e:
            self.status_label.setText(f"Failed to Send: {e}")
            self.status_label.setStyleSheet(f"color: {ACCENT_RED};")
            QMessageBox.critical(self, "Error", str(e))

    def closeEvent(self, event):
        if hasattr(self, 'status_listener'):
            self.status_listener.stop()
            self.status_listener.wait(2000)
        event.accept()


# ================= MAIN =================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_DEEP))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_CARD))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    app.setPalette(palette)

    window = CarOBU()
    window.show()
    sys.exit(app.exec())
