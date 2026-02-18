"""
Smart RSU Relay Server
======================
Receives enriched packets from ESP32 RSU (real hardware),
adds synthetic TPMS data, and distributes to:
  - Car2 OBU (UDP)
  - Hospital / Ambulance listener (UDP)
  - Dashboard (internal queue)
Also receives ACK from Car2 with ETA info.
"""

import socket
import json
import math
import random
import time
import threading
import queue
from datetime import datetime

# ================= CONFIG =================
LISTEN_PORT       = 5005              # Same port ESP32 forwards to
CAR2_IP           = "127.0.0.1"       # Car2 runs on same laptop as relay (Laptop 2)
CAR2_PORT         = 5006
HOSPITAL_IP       = "127.0.0.1"       # Hospital listener (change to mobile IP if needed)
HOSPITAL_PORT     = 5007
DASHBOARD_IP      = "192.168.137.161" # Dashboard on Laptop 1
DASHBOARD_PORT    = 5008
CAR1_IP           = "192.168.137.161" # Car1 OBU on Laptop 1
CAR1_STATUS_PORT  = 5009

# Shared queue for dashboard
dashboard_queue = queue.Queue()

# Store latest state
latest_data = {
    "sensor_data": None,
    "tpms_data": None,
    "emergency": None,
    "car2_ack": None,
    "car2_eta": None,
}


# ================= TPMS SYNTHETIC DATA =================
class TPMSGenerator:
    """Generates realistic TPMS data for 4 wheels."""

    def __init__(self):
        self.base_pressure = {"FL": 33.0, "FR": 33.5, "RL": 32.0, "RR": 32.5}
        self.base_temp = {"FL": 35.0, "FR": 36.0, "RL": 34.0, "RR": 35.5}
        self.tick = 0

    def generate(self):
        self.tick += 1
        tpms = {}
        for wheel in ["FL", "FR", "RL", "RR"]:
            # Pressure: slow drift + small random jitter
            drift = math.sin(self.tick * 0.05 + hash(wheel) % 10) * 1.5
            jitter = random.uniform(-0.3, 0.3)
            pressure = round(self.base_pressure[wheel] + drift + jitter, 1)

            # Temperature: increases slightly over time with jitter
            temp_drift = math.sin(self.tick * 0.03 + hash(wheel) % 7) * 5
            temp_jitter = random.uniform(-1.0, 1.0)
            temp = round(self.base_temp[wheel] + temp_drift + temp_jitter, 1)

            # Clamp values
            pressure = max(25.0, min(42.0, pressure))
            temp = max(20.0, min(90.0, temp))

            tpms[wheel] = {
                "pressure_psi": pressure,
                "temperature_c": temp,
                "status": "LOW" if pressure < 28 else "HIGH" if pressure > 38 else "OK"
            }
        return tpms


tpms_gen = TPMSGenerator()


# ================= HAVERSINE =================
def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two GPS coordinates."""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def calculate_eta(lat1, lon1, lat2, lon2, speed_kmh=40):
    """Calculate ETA in minutes assuming average speed."""
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    if speed_kmh <= 0:
        return 999
    time_hours = dist / speed_kmh
    return round(time_hours * 60, 1)


# ================= UDP SEND HELPER =================
def udp_send(data, ip, port):
    """Send a JSON packet via UDP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        message = json.dumps(data).encode()
        sock.sendto(message, (ip, port))
        sock.close()
        print(f"  → Sent to {ip}:{port}")
    except Exception as e:
        print(f"  ✗ Failed to send to {ip}:{port}: {e}")


# ================= HANDLE INCOMING FROM ESP32 =================
def handle_esp32_packet(data, addr):
    """Process enriched packet from ESP32 RSU."""
    print(f"\n{'='*60}")
    print(f"📡 Received from ESP32 RSU ({addr[0]}:{addr[1]})")
    print(f"{'='*60}")

    try:
        packet = json.loads(data.decode())
    except json.JSONDecodeError:
        print("  ✗ Invalid JSON from ESP32")
        return

    print(f"  Vehicle: {packet.get('vehicle_id', 'N/A')}")
    print(f"  Issue: {packet.get('issue', 'N/A')}")
    print(f"  Hop Trace: {packet.get('hop_trace', [])}")

    # Extract sensor data from ESP32's enrichment
    sensor_data = packet.get("rsu_environment", {})
    env_status = packet.get("environment_status", "Unknown")

    print(f"  Sensors → Temp: {sensor_data.get('temperature')}°C, "
          f"Hum: {sensor_data.get('humidity')}%, "
          f"Gas: {sensor_data.get('air_quality')}, "
          f"Light: {sensor_data.get('light_level')}")
    print(f"  Env Status: {env_status}")

    # Generate TPMS synthetic data
    tpms = tpms_gen.generate()
    packet["tpms_data"] = tpms
    packet["relay_timestamp"] = datetime.now().strftime("%H:%M:%S")

    # Add relay to hop trace
    if "hop_trace" in packet:
        if "RELAY" not in packet["hop_trace"]:
            packet["hop_trace"].append("RELAY")

    # Update latest state
    latest_data["sensor_data"] = sensor_data
    latest_data["tpms_data"] = tpms
    latest_data["emergency"] = {
        "vehicle_id": packet.get("vehicle_id"),
        "issue": packet.get("issue"),
        "raw_description": packet.get("raw_description"),
        "latitude": packet.get("latitude"),
        "longitude": packet.get("longitude"),
        "timestamp": packet.get("timestamp"),
        "hop_trace": packet.get("hop_trace"),
        "environment_status": env_status,
    }

    # Forward to Car2
    print("\n🚙 Forwarding to Car2...")
    udp_send(packet, CAR2_IP, CAR2_PORT)

    # Forward to Hospital
    hospital_msg = {
        "type": "EMERGENCY_ALERT",
        "vehicle_id": packet.get("vehicle_id"),
        "issue": packet.get("issue"),
        "raw_description": packet.get("raw_description"),
        "latitude": packet.get("latitude"),
        "longitude": packet.get("longitude"),
        "timestamp": packet.get("timestamp"),
        "environment_status": env_status,
        "maps_link": f"https://www.google.com/maps?q={packet.get('latitude')},{packet.get('longitude')}",
        "relay_timestamp": packet["relay_timestamp"],
    }
    print("🏥 Forwarding to Hospital/Ambulance...")
    udp_send(hospital_msg, HOSPITAL_IP, HOSPITAL_PORT)

    # Push to dashboard queue
    dashboard_msg = {
        "type": "EMERGENCY",
        "data": packet,
        "sensor_data": sensor_data,
        "tpms_data": tpms,
        "environment_status": env_status,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    dashboard_queue.put(dashboard_msg)

    # Also send to dashboard via UDP
    udp_send(dashboard_msg, DASHBOARD_IP, DASHBOARD_PORT)

    print(f"\n✅ Packet distributed to all endpoints")


# ================= HANDLE CAR2 ACK =================
def handle_car2_ack(data, addr):
    """Process acknowledgment from Car2."""
    print(f"\n{'='*60}")
    print(f"🚙 Received ACK from Car2 ({addr[0]}:{addr[1]})")
    print(f"{'='*60}")

    try:
        ack = json.loads(data.decode())
    except json.JSONDecodeError:
        print("  ✗ Invalid JSON from Car2")
        return

    if ack.get("type") != "ACK":
        return

    car2_lat = ack.get("car2_latitude", 0)
    car2_lon = ack.get("car2_longitude", 0)

    # Calculate ETA
    emergency = latest_data.get("emergency")
    if emergency:
        acc_lat = emergency.get("latitude", 0)
        acc_lon = emergency.get("longitude", 0)
        eta_min = calculate_eta(car2_lat, car2_lon, acc_lat, acc_lon)
        distance = haversine_distance(car2_lat, car2_lon, acc_lat, acc_lon)
    else:
        eta_min = 0
        distance = 0

    print(f"  Car2 Location: ({car2_lat}, {car2_lon})")
    print(f"  Distance: {distance:.2f} km")
    print(f"  ETA: {eta_min} minutes")

    latest_data["car2_ack"] = ack
    latest_data["car2_eta"] = eta_min

    # Notify Dashboard
    dashboard_ack = {
        "type": "CAR2_ACK",
        "car2_id": ack.get("car2_id", "CAR_02"),
        "car2_latitude": car2_lat,
        "car2_longitude": car2_lon,
        "eta_minutes": eta_min,
        "distance_km": round(distance, 2),
        "ack_timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    dashboard_queue.put(dashboard_ack)
    udp_send(dashboard_ack, DASHBOARD_IP, DASHBOARD_PORT)

    # Notify Car1 that help is coming
    car1_status = {
        "type": "HELP_COMING",
        "helper_id": ack.get("car2_id", "CAR_02"),
        "eta_minutes": eta_min,
        "distance_km": round(distance, 2),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    print("🚗 Notifying Car1 that help is on the way...")
    udp_send(car1_status, CAR1_IP, CAR1_STATUS_PORT)

    print(f"\n✅ ACK processed — ETA {eta_min} min sent to Dashboard + Car1")


# ================= TPMS PERIODIC BROADCAST =================
def tpms_broadcast_loop():
    """Periodically send TPMS data to dashboard."""
    while True:
        time.sleep(3)
        tpms = tpms_gen.generate()
        latest_data["tpms_data"] = tpms

        msg = {
            "type": "TPMS_UPDATE",
            "tpms_data": tpms,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        dashboard_queue.put(msg)
        udp_send(msg, DASHBOARD_IP, DASHBOARD_PORT)


# ================= MAIN LISTENER =================
def main():
    print("=" * 60)
    print("  📡 SMART RSU RELAY SERVER")
    print("=" * 60)
    print(f"  Listening on UDP port {LISTEN_PORT}")
    print(f"  Car2 target  → {CAR2_IP}:{CAR2_PORT}")
    print(f"  Hospital     → {HOSPITAL_IP}:{HOSPITAL_PORT}")
    print(f"  Dashboard    → {DASHBOARD_IP}:{DASHBOARD_PORT}")
    print(f"  Car1 status  → {CAR1_IP}:{CAR1_STATUS_PORT}")
    print("=" * 60)
    print("Waiting for packets from ESP32 RSU...\n")

    # Start TPMS broadcast thread
    tpms_thread = threading.Thread(target=tpms_broadcast_loop, daemon=True)
    tpms_thread.start()

    # Main UDP listener
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", LISTEN_PORT))

    # Secondary listener for Car2 ACK on a different port
    ack_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ack_sock.bind(("0.0.0.0", LISTEN_PORT + 10))  # Port 5015 for ACKs

    print(f"  ACK listener on port {LISTEN_PORT + 10}")

    def ack_listener():
        while True:
            data, addr = ack_sock.recvfrom(4096)
            handle_car2_ack(data, addr)

    ack_thread = threading.Thread(target=ack_listener, daemon=True)
    ack_thread.start()

    while True:
        data, addr = sock.recvfrom(4096)
        # Check if it's an ACK or an ESP32 packet
        try:
            pkt = json.loads(data.decode())
            if pkt.get("type") == "ACK":
                handle_car2_ack(data, addr)
            else:
                handle_esp32_packet(data, addr)
        except json.JSONDecodeError:
            print(f"  ✗ Invalid packet from {addr}")


if __name__ == "__main__":
    main()
