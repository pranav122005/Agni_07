"""
Smart RSU Command Center Dashboard
====================================
PyQt6 dashboard that displays:
  - Real sensor data from ESP32 (DHT11, MQ-135, LDR)
  - Synthetic TPMS data (4-wheel visualization)
  - Emergency alert feed with hop trace
  - Car2 ACK status + ETA countdown
  - Hospital notification status
  - Environment anomaly alerts
"""

import sys
import socket
import json
import math
import random
import time
import threading
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QFrame, QProgressBar, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QPalette, QPainter, QPen, QBrush, QLinearGradient


# ================= CONFIG =================
LISTEN_PORT = 5008

# ================= COLORS =================
BG_DEEP    = "#0A0F1E"
BG_PANEL   = "#0D1529"
BG_CARD    = "#111D35"
BG_CARD_ALT = "#0F1A30"
ACCENT_RED = "#E84545"
ACCENT_TEAL = "#00D4AA"
ACCENT_AMBER = "#F5A623"
ACCENT_BLUE = "#4A9EFF"
ACCENT_PURPLE = "#8B5CF6"
ACCENT_GREEN = "#22C55E"
TEXT_PRIMARY = "#E8EDF5"
TEXT_SECONDARY = "#7B8BAE"
TEXT_MUTED  = "#3D4F6E"
BORDER_CLR = "#1E2D4A"
BORDER_ACTIVE = "#2A4080"


# ================= UDP LISTENER THREAD =================
class DashboardListener(QThread):
    data_received = pyqtSignal(dict)

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
                data, addr = sock.recvfrom(8192)
                pkt = json.loads(data.decode())
                self.data_received.emit(pkt)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Dashboard listener error: {e}")

    def stop(self):
        self._running = False


# ================= CIRCULAR GAUGE WIDGET =================
class GaugeWidget(QWidget):
    """Custom circular gauge widget for sensor values."""

    def __init__(self, title, unit, min_val, max_val, warn_threshold=None,
                 color=ACCENT_TEAL, parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.min_val = min_val
        self.max_val = max_val
        self.warn_threshold = warn_threshold
        self.color = QColor(color)
        self.value = 0
        self.setFixedSize(160, 180)

    def set_value(self, val):
        self.value = max(self.min_val, min(self.max_val, val))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2 - 10
        radius = 58

        # Background arc
        pen = QPen(QColor(BORDER_CLR), 8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(cx - radius, cy - radius, radius * 2, radius * 2,
                        225 * 16, -270 * 16)

        # Value arc
        pct = (self.value - self.min_val) / max(1, self.max_val - self.min_val)
        pct = max(0, min(1, pct))

        # Color based on threshold
        if self.warn_threshold and self.value > self.warn_threshold:
            arc_color = QColor(ACCENT_RED)
        else:
            arc_color = self.color

        pen = QPen(arc_color, 8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        span = int(-270 * pct * 16)
        painter.drawArc(cx - radius, cy - radius, radius * 2, radius * 2,
                        225 * 16, span)

        # Glow effect (subtle)
        glow_color = QColor(arc_color)
        glow_color.setAlpha(30)
        pen = QPen(glow_color, 16)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(cx - radius, cy - radius, radius * 2, radius * 2,
                        225 * 16, span)

        # Value text
        painter.setPen(QColor(TEXT_PRIMARY))
        font = QFont("Segoe UI", 18, QFont.Weight.Bold)
        painter.setFont(font)
        val_text = f"{self.value:.1f}" if isinstance(self.value, float) else str(int(self.value))
        painter.drawText(cx - 40, cy - 8, 80, 30,
                         Qt.AlignmentFlag.AlignCenter, val_text)

        # Unit text
        painter.setPen(QColor(TEXT_MUTED))
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        painter.drawText(cx - 40, cy + 16, 80, 20,
                         Qt.AlignmentFlag.AlignCenter, self.unit)

        # Title text
        painter.setPen(QColor(TEXT_SECONDARY))
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(0, h - 22, w, 20,
                         Qt.AlignmentFlag.AlignCenter, self.title)

        painter.end()


# ================= TPMS WHEEL WIDGET =================
class TPMSWheelWidget(QWidget):
    """Shows a single tire with pressure and temperature."""

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.label = label
        self.pressure = 0
        self.temperature = 0
        self.status = "OK"
        self.setFixedSize(110, 100)

    def set_data(self, pressure, temperature, status):
        self.pressure = pressure
        self.temperature = temperature
        self.status = status
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Background
        if self.status == "LOW":
            bg = QColor(ACCENT_RED)
            bg.setAlpha(30)
            border = QColor(ACCENT_RED)
        elif self.status == "HIGH":
            bg = QColor(ACCENT_AMBER)
            bg.setAlpha(30)
            border = QColor(ACCENT_AMBER)
        else:
            bg = QColor(ACCENT_TEAL)
            bg.setAlpha(15)
            border = QColor(BORDER_CLR)

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(4, 4, w - 8, h - 8, 10, 10)

        # Wheel label
        painter.setPen(QColor(TEXT_MUTED))
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.drawText(10, 18, self.label)

        # Tire icon
        painter.setPen(QColor(TEXT_PRIMARY))
        painter.setFont(QFont("Segoe UI", 16))
        painter.drawText(w - 35, 24, "🛞")

        # Pressure
        color = ACCENT_RED if self.status == "LOW" else ACCENT_TEAL
        painter.setPen(QColor(color))
        painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        painter.drawText(10, 50, f"{self.pressure:.1f}")
        painter.setPen(QColor(TEXT_MUTED))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(10, 64, "PSI")

        # Temperature
        painter.setPen(QColor(ACCENT_AMBER))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(10, 85, f"{self.temperature:.0f}°C")

        painter.end()


# ================= MAIN DASHBOARD =================
class Dashboard(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("◈ Smart RSU — Command Center")
        self.setMinimumSize(1100, 720)

        # State
        self.sensor_data = {"temperature": 0, "humidity": 0, "air_quality": 0, "light_level": 0}
        self.tpms_data = {}
        self.emergency_list = []
        self.car2_status = None
        self.env_status = "Normal"

        self.init_ui()
        self.start_listener()

    def init_ui(self):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_DEEP};
                color: {TEXT_PRIMARY};
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }}
            QScrollBar:vertical {{
                background: {BG_PANEL};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER_ACTIVE};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── HEADER BAR ──
        header = QFrame()
        header.setFixedHeight(56)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_PANEL};
                border-bottom: 1px solid {BORDER_CLR};
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("◈ SMART RSU — COMMAND CENTER")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT_AMBER}; letter-spacing: 3px;")
        h_layout.addWidget(title)

        h_layout.addStretch()

        self.live_dot = QLabel("● LIVE")
        self.live_dot.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.live_dot.setStyleSheet(f"color: {ACCENT_TEAL};")
        h_layout.addWidget(self.live_dot)

        # Clock
        self.clock_label = QLabel("")
        self.clock_label.setFont(QFont("Segoe UI", 10))
        self.clock_label.setStyleSheet(f"color: {TEXT_SECONDARY}; margin-left: 16px;")
        h_layout.addWidget(self.clock_label)

        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.update_clock()

        main_layout.addWidget(header)

        # ── BODY ──
        body = QFrame()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(12)

        # ── ROW 1: SENSOR GAUGES ──
        sensor_row = QHBoxLayout()
        sensor_row.setSpacing(12)

        self.temp_gauge = GaugeWidget("TEMPERATURE", "°C", 0, 60,
                                       warn_threshold=45, color=ACCENT_RED)
        self.hum_gauge = GaugeWidget("HUMIDITY", "%", 0, 100,
                                      color=ACCENT_BLUE)
        self.gas_gauge = GaugeWidget("AIR QUALITY", "PPM", 0, 4095,
                                      warn_threshold=2000, color=ACCENT_PURPLE)
        self.light_gauge = GaugeWidget("LIGHT LEVEL", "lux", 0, 4095,
                                        color=ACCENT_AMBER)

        for gauge in [self.temp_gauge, self.hum_gauge, self.gas_gauge, self.light_gauge]:
            card = self._gauge_card(gauge)
            sensor_row.addWidget(card)

        sensor_row.addStretch()
        body_layout.addLayout(sensor_row)

        # ── ROW 2: TPMS + ALERTS ──
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        # TPMS Panel
        tpms_card = self._make_card("🛞 TPMS MONITOR")
        tpms_layout = tpms_card.layout()

        tpms_grid = QGridLayout()
        tpms_grid.setSpacing(8)

        self.tpms_fl = TPMSWheelWidget("FRONT LEFT")
        self.tpms_fr = TPMSWheelWidget("FRONT RIGHT")
        self.tpms_rl = TPMSWheelWidget("REAR LEFT")
        self.tpms_rr = TPMSWheelWidget("REAR RIGHT")

        tpms_grid.addWidget(self.tpms_fl, 0, 0)
        tpms_grid.addWidget(self.tpms_fr, 0, 1)

        # Car icon between rows
        car_icon = QLabel("🚗")
        car_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        car_icon.setFont(QFont("Segoe UI", 28))
        tpms_grid.addWidget(car_icon, 1, 0, 1, 2)

        tpms_grid.addWidget(self.tpms_rl, 2, 0)
        tpms_grid.addWidget(self.tpms_rr, 2, 1)

        tpms_layout.addLayout(tpms_grid)
        row2.addWidget(tpms_card)

        # Emergency + Car2 Status Panel
        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)

        # Environment Status
        self.env_card = self._make_card("🌍 ENVIRONMENT STATUS")
        env_layout = self.env_card.layout()
        self.env_status_label = QLabel("Normal Environment")
        self.env_status_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.env_status_label.setStyleSheet(f"color: {ACCENT_TEAL};")
        env_layout.addWidget(self.env_status_label)
        right_panel.addWidget(self.env_card)

        # Car2 ACK Status
        self.car2_card = self._make_card("🚙 CAR2 RESPONSE")
        car2_layout = self.car2_card.layout()

        self.car2_status_label = QLabel("Waiting for response...")
        self.car2_status_label.setFont(QFont("Segoe UI", 11))
        self.car2_status_label.setStyleSheet(f"color: {TEXT_MUTED};")
        car2_layout.addWidget(self.car2_status_label)

        self.car2_eta_label = QLabel("")
        self.car2_eta_label.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.car2_eta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.car2_eta_label.setStyleSheet(f"color: {ACCENT_AMBER};")
        car2_layout.addWidget(self.car2_eta_label)

        self.car2_dist_label = QLabel("")
        self.car2_dist_label.setFont(QFont("Segoe UI", 10))
        self.car2_dist_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        car2_layout.addWidget(self.car2_dist_label)

        right_panel.addWidget(self.car2_card)

        # Hospital Status
        self.hospital_card = self._make_card("🏥 HOSPITAL NOTIFICATION")
        hosp_layout = self.hospital_card.layout()
        self.hospital_status = QLabel("No active emergencies")
        self.hospital_status.setFont(QFont("Segoe UI", 10))
        self.hospital_status.setStyleSheet(f"color: {TEXT_MUTED};")
        hosp_layout.addWidget(self.hospital_status)
        right_panel.addWidget(self.hospital_card)

        row2.addLayout(right_panel, 1)
        body_layout.addLayout(row2, 1)

        # ── ROW 3: EMERGENCY FEED ──
        feed_card = self._make_card("🚨 EMERGENCY FEED")
        feed_layout = feed_card.layout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(160)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.feed_container = QWidget()
        self.feed_layout = QVBoxLayout(self.feed_container)
        self.feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.feed_layout.setSpacing(6)
        scroll.setWidget(self.feed_container)

        waiting = QLabel("📡 Monitoring for emergency alerts...")
        waiting.setFont(QFont("Segoe UI", 10))
        waiting.setStyleSheet(f"color: {TEXT_MUTED};")
        self.feed_layout.addWidget(waiting)
        self.waiting_feed_label = waiting

        feed_layout.addWidget(scroll)
        body_layout.addWidget(feed_card)

        main_layout.addWidget(body, 1)

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

    def _gauge_card(self, gauge_widget):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_CLR};
                border-radius: 12px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(8, 8, 8, 8)
        cl.addWidget(gauge_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        return card

    def update_clock(self):
        self.clock_label.setText(datetime.now().strftime("%H:%M:%S   %d %b %Y"))

    # ================= LISTENER =================
    def start_listener(self):
        self.listener = DashboardListener(LISTEN_PORT)
        self.listener.data_received.connect(self.on_data_received)
        self.listener.start()

    def on_data_received(self, packet):
        msg_type = packet.get("type", "")

        if msg_type == "EMERGENCY":
            self.handle_emergency(packet)
        elif msg_type == "TPMS_UPDATE":
            self.update_tpms(packet.get("tpms_data", {}))
        elif msg_type == "CAR2_ACK":
            self.handle_car2_ack(packet)
        else:
            # Try to extract sensor data from any packet
            if "sensor_data" in packet:
                self.update_sensors(packet["sensor_data"])
            if "tpms_data" in packet:
                self.update_tpms(packet["tpms_data"])

    def handle_emergency(self, packet):
        data = packet.get("data", {})
        sensor = packet.get("sensor_data", {})
        tpms = packet.get("tpms_data", {})
        env = packet.get("environment_status", "Unknown")

        # Update sensors
        self.update_sensors(sensor)

        # Update TPMS
        self.update_tpms(tpms)

        # Update environment
        self.env_status = env
        self.update_env_display()

        # Add to feed
        self.add_emergency_feed(data)

        # Update hospital status
        self.hospital_status.setText(f"✅ Alert sent for {data.get('vehicle_id', '?')} — GPS dispatched")
        self.hospital_status.setStyleSheet(f"color: {ACCENT_TEAL};")

        # Flash live indicator
        self.live_dot.setStyleSheet(f"color: {ACCENT_RED};")
        QTimer.singleShot(2000, lambda: self.live_dot.setStyleSheet(f"color: {ACCENT_TEAL};"))

    def update_sensors(self, sensor):
        if not sensor:
            return

        temp = sensor.get("temperature", 0)
        hum = sensor.get("humidity", 0)
        gas = sensor.get("air_quality", 0)
        light = sensor.get("light_level", 0)

        if temp and not (isinstance(temp, float) and math.isnan(temp)):
            self.temp_gauge.set_value(float(temp))
        if hum and not (isinstance(hum, float) and math.isnan(hum)):
            self.hum_gauge.set_value(float(hum))
        self.gas_gauge.set_value(int(gas) if gas else 0)
        self.light_gauge.set_value(int(light) if light else 0)

    def update_tpms(self, tpms):
        if not tpms:
            return

        mapping = {"FL": self.tpms_fl, "FR": self.tpms_fr,
                    "RL": self.tpms_rl, "RR": self.tpms_rr}
        for key, widget in mapping.items():
            if key in tpms:
                d = tpms[key]
                widget.set_data(
                    d.get("pressure_psi", 0),
                    d.get("temperature_c", 0),
                    d.get("status", "OK")
                )

    def update_env_display(self):
        if "Fire" in self.env_status:
            self.env_status_label.setText(f"🔥 {self.env_status}")
            self.env_status_label.setStyleSheet(f"color: {ACCENT_RED};")
            self.env_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {BG_CARD};
                    border: 2px solid {ACCENT_RED};
                    border-radius: 12px;
                }}
            """)
        elif "Low Visibility" in self.env_status:
            self.env_status_label.setText(f"🌫️ {self.env_status}")
            self.env_status_label.setStyleSheet(f"color: {ACCENT_AMBER};")
            self.env_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {BG_CARD};
                    border: 2px solid {ACCENT_AMBER};
                    border-radius: 12px;
                }}
            """)
        else:
            self.env_status_label.setText(f"✅ {self.env_status}")
            self.env_status_label.setStyleSheet(f"color: {ACCENT_TEAL};")
            self.env_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {BG_CARD};
                    border: 1px solid {BORDER_CLR};
                    border-radius: 12px;
                }}
            """)

    def add_emergency_feed(self, data):
        if self.waiting_feed_label:
            self.waiting_feed_label.hide()
            self.waiting_feed_label = None

        vehicle = data.get("vehicle_id", "Unknown")
        issue = data.get("issue", "Unknown")
        raw = data.get("raw_description", "")
        lat = data.get("latitude", 0)
        lon = data.get("longitude", 0)
        hop = data.get("hop_trace", [])
        ts = data.get("timestamp", "")

        # Create feed item
        item = QFrame()
        item.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(232, 69, 69, 0.08);
                border: 1px solid {ACCENT_RED};
                border-radius: 8px;
            }}
        """)
        il = QHBoxLayout(item)
        il.setContentsMargins(12, 8, 12, 8)
        il.setSpacing(16)

        # Left info
        left = QVBoxLayout()
        left.setSpacing(2)

        title_lbl = QLabel(f"🚨 {vehicle} — {issue}")
        title_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {ACCENT_RED};")
        left.addWidget(title_lbl)

        desc_lbl = QLabel(f"📝 {raw}")
        desc_lbl.setFont(QFont("Segoe UI", 9))
        desc_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        left.addWidget(desc_lbl)

        gps_lbl = QLabel(f"📍 GPS: {lat}, {lon}")
        gps_lbl.setFont(QFont("Segoe UI", 9))
        gps_lbl.setStyleSheet(f"color: {ACCENT_BLUE};")
        left.addWidget(gps_lbl)

        il.addLayout(left, 1)

        # Right: hop trace + time
        right = QVBoxLayout()
        right.setSpacing(2)
        right.setAlignment(Qt.AlignmentFlag.AlignRight)

        time_lbl = QLabel(ts)
        time_lbl.setFont(QFont("Segoe UI", 9))
        time_lbl.setStyleSheet(f"color: {TEXT_MUTED};")
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(time_lbl)

        hop_lbl = QLabel(" → ".join(hop))
        hop_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        hop_lbl.setStyleSheet(f"color: {ACCENT_AMBER};")
        hop_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(hop_lbl)

        il.addLayout(right)

        self.feed_layout.insertWidget(0, item)

    def handle_car2_ack(self, packet):
        car2_id = packet.get("car2_id", "CAR_02")
        eta = packet.get("eta_minutes", "?")
        dist = packet.get("distance_km", "?")
        ts = packet.get("ack_timestamp", "")

        self.car2_status_label.setText(f"✅ {car2_id} acknowledged at {ts}")
        self.car2_status_label.setStyleSheet(f"color: {ACCENT_TEAL};")

        self.car2_eta_label.setText(f"ETA: {eta} min")
        self.car2_dist_label.setText(f"📏 Distance: {dist} km")

        self.car2_card.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 2px solid {ACCENT_TEAL};
                border-radius: 12px;
            }}
        """)

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

    window = Dashboard()
    window.show()
    sys.exit(app.exec())
