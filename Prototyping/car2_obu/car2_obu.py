"""
Car 2 On-Board Unit (OBU)
=========================
Receives emergency alerts from Relay Server,
displays popup, lets driver acknowledge,
calculates ETA and sends ACK back.
"""

import sys
import socket
import json
import math
import threading
import geocoder
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QMessageBox, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon


# ================= CONFIG =================
LISTEN_PORT       = 5006          # Receives from relay
RELAY_IP          = "127.0.0.1"
RELAY_ACK_PORT    = 5015          # Send ACK back to relay
VEHICLE_ID        = "CAR_02"

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


# ================= HAVERSINE =================
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def calculate_eta(lat1, lon1, lat2, lon2, speed_kmh=40):
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    if speed_kmh <= 0:
        return 999, dist
    time_min = (dist / speed_kmh) * 60
    return round(time_min, 1), round(dist, 2)


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
class Car2OBU(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🚙 Car 2 — On-Board Unit")
        self.setFixedSize(520, 700)
        self.pending_emergency = None
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

        title = QLabel("◈ CAR 2 — OBU")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT_AMBER}; letter-spacing: 2px;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        self.status_dot = QLabel("● MONITORING")
        self.status_dot.setFont(QFont("Segoe UI", 9))
        self.status_dot.setStyleSheet(f"color: {ACCENT_TEAL};")
        h_layout.addWidget(self.status_dot)

        layout.addWidget(header)

        # ── BODY ──
        body = QFrame()
        body.setStyleSheet(f"background-color: {BG_DEEP};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        body_layout.setSpacing(16)

        # Vehicle info card
        info_card = self._make_card("VEHICLE INFO")
        info_layout = info_card.layout()
        self.vehicle_label = QLabel(f"Vehicle ID: {VEHICLE_ID}")
        self.vehicle_label.setFont(QFont("Segoe UI", 11))
        self.vehicle_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        info_layout.addWidget(self.vehicle_label)

        self.gps_label = QLabel("GPS: Fetching...")
        self.gps_label.setFont(QFont("Segoe UI", 10))
        self.gps_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        info_layout.addWidget(self.gps_label)
        body_layout.addWidget(info_card)

        # Fetch GPS
        self.my_lat, self.my_lon = 0, 0
        QTimer.singleShot(500, self.fetch_gps)

        # Alert card (hidden until alert)
        self.alert_card = self._make_card("🚨 INCOMING EMERGENCY")
        self.alert_card.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 2px solid {ACCENT_RED};
                border-radius: 12px;
            }}
        """)
        alert_layout = self.alert_card.layout()

        self.alert_vehicle = QLabel("")
        self.alert_vehicle.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.alert_vehicle.setStyleSheet(f"color: {ACCENT_RED};")
        alert_layout.addWidget(self.alert_vehicle)

        self.alert_issue = QLabel("")
        self.alert_issue.setFont(QFont("Segoe UI", 11))
        self.alert_issue.setStyleSheet(f"color: {TEXT_PRIMARY};")
        alert_layout.addWidget(self.alert_issue)

        self.alert_desc = QLabel("")
        self.alert_desc.setFont(QFont("Segoe UI", 10))
        self.alert_desc.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self.alert_desc.setWordWrap(True)
        alert_layout.addWidget(self.alert_desc)

        self.alert_location = QLabel("")
        self.alert_location.setFont(QFont("Segoe UI", 10))
        self.alert_location.setStyleSheet(f"color: {ACCENT_BLUE};")
        alert_layout.addWidget(self.alert_location)

        self.alert_env = QLabel("")
        self.alert_env.setFont(QFont("Segoe UI", 10))
        self.alert_env.setStyleSheet(f"color: {ACCENT_AMBER};")
        alert_layout.addWidget(self.alert_env)

        self.alert_hop = QLabel("")
        self.alert_hop.setFont(QFont("Segoe UI", 9))
        self.alert_hop.setStyleSheet(f"color: {TEXT_MUTED};")
        alert_layout.addWidget(self.alert_hop)

        # ACK Button
        self.ack_button = QPushButton("✅  ACKNOWLEDGE — I WILL HELP")
        self.ack_button.setFixedHeight(50)
        self.ack_button.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.ack_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_TEAL};
                color: {BG_DEEP};
                border: none;
                border-radius: 12px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: #00E8BB;
            }}
            QPushButton:pressed {{
                background-color: #00B894;
            }}
        """)
        self.ack_button.clicked.connect(self.acknowledge_emergency)
        alert_layout.addWidget(self.ack_button)

        # ETA display
        self.eta_label = QLabel("")
        self.eta_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.eta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.eta_label.setStyleSheet(f"color: {ACCENT_AMBER};")
        alert_layout.addWidget(self.eta_label)

        self.alert_card.hide()
        body_layout.addWidget(self.alert_card)

        # Message log
        log_card = self._make_card("MESSAGE LOG")
        log_layout = log_card.layout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)
        self.log_container = QWidget()
        self.log_layout = QVBoxLayout(self.log_container)
        self.log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.log_layout.setSpacing(6)
        scroll.setWidget(self.log_container)
        log_layout.addWidget(scroll)
        body_layout.addWidget(log_card, 1)

        layout.addWidget(body, 1)
        self.add_log("System started — monitoring for emergency alerts...", TEXT_SECONDARY)

    def _make_card(self, title_text):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_CLR};
                border-radius: 12px;
            }}
        """)
        clayout = QVBoxLayout(card)
        clayout.setContentsMargins(16, 12, 16, 12)
        clayout.setSpacing(8)
        label = QLabel(title_text)
        label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")
        clayout.addWidget(label)
        return card

    def add_log(self, text, color=TEXT_SECONDARY):
        ts = datetime.now().strftime("%H:%M:%S")
        lbl = QLabel(f"[{ts}] {text}")
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet(f"color: {color};")
        lbl.setWordWrap(True)
        self.log_layout.addWidget(lbl)

    def fetch_gps(self):
        try:
            g = geocoder.ip('me')
            if g.ok:
                self.my_lat, self.my_lon = g.latlng
                self.gps_label.setText(f"GPS: {self.my_lat:.6f}, {self.my_lon:.6f}")
            else:
                self.gps_label.setText("GPS: Could not fetch (using default)")
                self.my_lat, self.my_lon = 28.6139, 77.2090  # Default Delhi
        except:
            self.gps_label.setText("GPS: Error (using default)")
            self.my_lat, self.my_lon = 28.6139, 77.2090

    def start_listener(self):
        self.listener = UDPListenerThread(LISTEN_PORT)
        self.listener.message_received.connect(self.on_message_received)
        self.listener.start()

    def on_message_received(self, packet):
        vehicle_id = packet.get("vehicle_id", "Unknown")
        issue = packet.get("issue", "Unknown")
        raw_desc = packet.get("raw_description", "No description")
        lat = packet.get("latitude", 0)
        lon = packet.get("longitude", 0)
        env_status = packet.get("environment_status", "Unknown")
        hop_trace = packet.get("hop_trace", [])

        self.pending_emergency = packet

        # Update UI
        self.status_dot.setText("● EMERGENCY RECEIVED")
        self.status_dot.setStyleSheet(f"color: {ACCENT_RED};")

        self.alert_vehicle.setText(f"Vehicle: {vehicle_id}")
        self.alert_issue.setText(f"Issue: {issue}")
        self.alert_desc.setText(f"Description: {raw_desc}")
        self.alert_location.setText(f"📍 Location: {lat}, {lon}")
        self.alert_env.setText(f"🌍 Environment: {env_status}")
        self.alert_hop.setText(f"Hop Trace: {' → '.join(hop_trace)}")
        self.eta_label.setText("")
        self.ack_button.setEnabled(True)
        self.ack_button.setText("✅  ACKNOWLEDGE — I WILL HELP")

        self.alert_card.show()

        self.add_log(f"🚨 EMERGENCY from {vehicle_id}: {issue}", ACCENT_RED)
        self.add_log(f"   Location: ({lat}, {lon})", ACCENT_BLUE)

    def acknowledge_emergency(self):
        if not self.pending_emergency:
            return

        pkt = self.pending_emergency
        acc_lat = pkt.get("latitude", 0)
        acc_lon = pkt.get("longitude", 0)

        eta_min, distance = calculate_eta(self.my_lat, self.my_lon, acc_lat, acc_lon)

        # Send ACK to relay
        ack_packet = {
            "type": "ACK",
            "car2_id": VEHICLE_ID,
            "car2_latitude": self.my_lat,
            "car2_longitude": self.my_lon,
            "accident_vehicle": pkt.get("vehicle_id"),
            "eta_minutes": eta_min,
            "distance_km": distance,
            "ack_timestamp": datetime.now().strftime("%H:%M:%S"),
        }

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            msg = json.dumps(ack_packet).encode()
            sock.sendto(msg, (RELAY_IP, RELAY_ACK_PORT))
            sock.close()

            self.ack_button.setText("✅  ACKNOWLEDGED")
            self.ack_button.setEnabled(False)
            self.ack_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {TEXT_MUTED};
                    color: {TEXT_PRIMARY};
                    border: none;
                    border-radius: 12px;
                }}
            """)

            self.eta_label.setText(f"🕐 ETA: {eta_min} min  |  📏 Distance: {distance} km")

            self.status_dot.setText("● RESPONDING")
            self.status_dot.setStyleSheet(f"color: {ACCENT_AMBER};")

            self.add_log(f"✅ Acknowledged — ETA: {eta_min} min, Distance: {distance} km", ACCENT_TEAL)

        except Exception as e:
            self.add_log(f"❌ Failed to send ACK: {e}", ACCENT_RED)

    def closeEvent(self, event):
        if hasattr(self, 'listener'):
            self.listener.stop()
            self.listener.wait(2000)
        event.accept()


# ================= MAIN =================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Apply dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_DEEP))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_CARD))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    app.setPalette(palette)

    window = Car2OBU()
    window.show()
    sys.exit(app.exec())
