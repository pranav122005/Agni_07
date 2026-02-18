import socket
import json

PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", PORT))

print("HOP_1 Running... Waiting for packets...\n")

while True:
    data, addr = sock.recvfrom(4096)
    packet = json.loads(data.decode())

    print("Packet received from RSU:")
    print(packet)
    print("\n")