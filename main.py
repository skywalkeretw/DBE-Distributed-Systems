
import socket
from threading import Thread
from multiprocessing import Process
import os
from uuid import uuid4
import json

hostname=socket.gethostname()
IPAddr=socket.gethostbyname(socket.gethostname()+'.')

server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

server_address = IPAddr #'127.0.0.1'
client_address = '192.168.178.30'
server_port = 10001
buffer_size = 4069
client_id = str(uuid4())
participants = []

def encode_data(d):
    return json.dumps(d).encode('utf-8')
def decode_data(d):
    json.loads(d.decode('utf-8'))

def receive_messages():
    server_socket.bind((server_address, server_port))
    
    while True:
        data, address = server_socket.recvfrom(buffer_size)
        print(f"{address[0]}: {data.decode()}" )

def send_messages():
    while True:
        msg = input()
        for participant in participants:
            client_socket.sendto(msg.encode(), (participant["ip"], server_port))

# echo -n "test data" | nc -u -b 255.255.255.255 10001
def join_chat():
    data = {
        "id": client_id,
        "ip": IPAddr
    }
    broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    #s.sendto(str.encode(IPAddr), ("192.168.178.255", server_port))
    broadcast_socket.sendto(encode_data(data), ("255.255.255.255", server_port))

# nc -luk 10001
def listen_for_participants():
    s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    broadcast_socket.bind(('',server_port))
    while True:
        new_participant, address = broadcast_socket.recvfrom(buffer_size)
        new_participant = decode_data(new_participant)
        participants.append(new_participant)


if __name__ == '__main__':
    #join_chat()

    Thread(target=listen_for_participants).start()
    # Thread(target=receive_messages).start()
    # Thread(target=send_messages).start
    print("server Running")

    print("Your Computer Name is: "+hostname)
    print("Your Computer IP Address is: "+IPAddr)

