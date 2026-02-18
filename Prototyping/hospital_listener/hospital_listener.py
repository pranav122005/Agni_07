"""
Hospital / Ambulance Emergency Listener
========================================
Receives emergency GPS alerts from RSU Relay Server.
Displays vehicle info, issue, GPS location with Google Maps link.
Simulates a hospital/ambulance dispatch notification system.
"""

import sys
import socket
import json
import webbrowser
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QColor, QPalette, QDesktopServices


# ================= CONFIG =================
LISTEN_PORT = 5007

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


# ================= UDP LISTENER THREAD =================
class UDPListenerThread(QThread):
    message_received = pyqtSignal(dict)

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
                self.message_received.emit(pkt)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Listener error: {e}")

    def stop(self):
        self._running = False


# ================= MAIN WINDOW =================
class HospitalListener(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🏥 Hospital — Emergency Dispatch")
        self.setFixedSize(480, 650)
        self.alert_count = 0
        self.init_ui()
        self.start_listener()

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

        title = QLabel("🏥 HOSPITAL DISPATCH")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT_RED}; letter-spacing: 2px;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        self.status_label = QLabel("● LISTENING")
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setStyleSheet(f"color: {ACCENT_TEAL};")
        h_layout.addWidget(self.status_label)

        layout.addWidget(header)

        # ── BODY ──
        body = QFrame()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        body_layout.setSpacing(16)

        # Stats bar
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_CLR};
                border-radius: 10px;
            }}
        """)
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(16, 10, 16, 10)

        self.alert_count_label = QLabel("Alerts: 0")
        self.alert_count_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.alert_count_label.setStyleSheet(f"color: {ACCENT_AMBER};")
        stats_layout.addWidget(self.alert_count_label)

        stats_layout.addStretch()

        port_label = QLabel(f"Port: {LISTEN_PORT}")
        port_label.setFont(QFont("Segoe UI", 9))
        port_label.setStyleSheet(f"color: {TEXT_MUTED};")
        stats_layout.addWidget(port_label)

        body_layout.addWidget(stats_frame)

        # Alerts scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)
        self.alerts_container = QWidget()
        self.alerts_layout = QVBoxLayout(self.alerts_container)
        self.alerts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.alerts_layout.setSpacing(12)
        scroll.setWidget(self.alerts_container)
        body_layout.addWidget(scroll, 1)

        # Waiting label
        self.waiting_label = QLabel("📡 Waiting for emergency alerts...")
        self.waiting_label.setFont(QFont("Segoe UI", 11))
        self.waiting_label.setStyleSheet(f"color: {TEXT_MUTED};")
        self.waiting_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alerts_layout.addWidget(self.waiting_label)

        layout.addWidget(body, 1)

    def start_listener(self):
        self.listener = UDPListenerThread(LISTEN_PORT)
        self.listener.message_received.connect(self.on_alert_received)
        self.listener.start()

    def on_alert_received(self, packet):
        self.waiting_label.hide()
        self.alert_count += 1
        self.alert_count_label.setText(f"Alerts: {self.alert_count}")

        self.status_label.setText("● ALERT RECEIVED")
        self.status_label.setStyleSheet(f"color: {ACCENT_RED};")

        vehicle_id = packet.get("vehicle_id", "Unknown")
        issue = packet.get("issue", "Unknown")
        raw_desc = packet.get("raw_description", "No description")
        lat = packet.get("latitude", 0)
        lon = packet.get("longitude", 0)
        env_status = packet.get("environment_status", "Unknown")
        maps_link = packet.get("maps_link", f"https://www.google.com/maps?q={lat},{lon}")
        timestamp = packet.get("relay_timestamp", datetime.now().strftime("%H:%M:%S"))

        # Build alert card
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 2px solid {ACCENT_RED};
                border-radius: 12px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(6)

        # Header row
        header_row = QHBoxLayout()
        alert_title = QLabel(f"🚨 EMERGENCY #{self.alert_count}")
        alert_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        alert_title.setStyleSheet(f"color: {ACCENT_RED};")
        header_row.addWidget(alert_title)
        header_row.addStretch()
        time_label = QLabel(timestamp)
        time_label.setFont(QFont("Segoe UI", 9))
        time_label.setStyleSheet(f"color: {TEXT_MUTED};")
        header_row.addWidget(time_label)
        card_layout.addLayout(header_row)

        # Details
        details = [
            (f"🚗 Vehicle: {vehicle_id}", TEXT_PRIMARY),
            (f"⚠️ Issue: {issue}", ACCENT_AMBER),
            (f"📝 Description: {raw_desc}", TEXT_SECONDARY),
            (f"📍 GPS: {lat}, {lon}", ACCENT_BLUE),
            (f"🌍 Environment: {env_status}", TEXT_SECONDARY),
        ]
        for text, color in details:
            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setStyleSheet(f"color: {color};")
            lbl.setWordWrap(True)
            card_layout.addWidget(lbl)

        # Open Maps button
        maps_btn = QPushButton("📍 OPEN IN GOOGLE MAPS")
        maps_btn.setFixedHeight(38)
        maps_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        maps_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_BLUE};
                color: white;
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: #5BADFF;
            }}
        """)
        maps_btn.clicked.connect(lambda checked, link=maps_link: QDesktopServices.openUrl(QUrl(link)))
        card_layout.addWidget(maps_btn)

        # Dispatch button
        dispatch_btn = QPushButton("🚑 DISPATCH AMBULANCE")
        dispatch_btn.setFixedHeight(38)
        dispatch_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        dispatch_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_RED};
                color: white;
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: #F05555;
            }}
        """)
        dispatch_btn.clicked.connect(
            lambda checked, btn=dispatch_btn: self.dispatch_ambulance(btn)
        )
        card_layout.addWidget(dispatch_btn)

        # Insert at top
        self.alerts_layout.insertWidget(0, card)

    def dispatch_ambulance(self, btn):
        btn.setText("🚑 AMBULANCE DISPATCHED ✅")
        btn.setEnabled(False)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {TEXT_MUTED};
                color: {TEXT_PRIMARY};
                border: none;
                border-radius: 8px;
            }}
        """)
        self.status_label.setText("● AMBULANCE DISPATCHED")
        self.status_label.setStyleSheet(f"color: {ACCENT_TEAL};")

    def closeEvent(self, event):
        if hasattr(self, 'listener'):
            self.listener.stop()
            self.listener.wait(2000)
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

    window = HospitalListener()
    window.show()
    sys.exit(app.exec())
