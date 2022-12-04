
import socket
from threading import Thread
from multiprocessing import Process
import os
from uuid import uuid4
import json

hostname=socket.gethostname()
IPAddr=socket.gethostbyname(socket.gethostname()+'.')


# broadcast sockets
broadcast_server_socket, broadcast_client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) , socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
broadcast_port = 10001
#chat sockets
chat_server_socket, chat_client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) , socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
chat_port = 10002
#info sockets TCP
info_server_socket, info_client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) , socket.socket(socket.AF_INET, socket.SOCK_STREAM)
info_port = 10003

server_address = IPAddr #'127.0.0.1'

buffer_size = 4069
client_id = str(uuid4())
participants = []
participant_data = {
        "id": client_id,
        "ip": IPAddr
    }
#-------------------------------------------------------------------------------------------------------

# helper functions

def encode_data(d):
    return json.dumps(d).encode('utf-8')

def decode_data(d):
    return json.loads(d.decode('utf-8'))

def sort_participants(participants):
    return sorted(participants, key=lambda d: d['id'])

def get_neighbour(ring, uid, direction='left'):
    current_index = next((index for (index, d) in enumerate(participants) if d["id"] == uid), None)
    if current_index != -1:
        if direction == 'left':
            if current_index + 1 == len(ring):
                return ring[0]
            else:
                return ring[current_index + 1]
        else:
            if current_index == 0:
                return ring[len(ring)-1]
            else:
                return ring[current_index -1]
    else:
        return None

# print(get_neighbour(participants,"14ede406-ccde-48f4-b05d-62cae9fd0bda"))

#-------------------------------------------------------------------------------------------------------

# Broadcast to Join the chat

# echo -n "test data" | nc -u -b 255.255.255.255 10001
def join_chat():
    data = participant_data
    broadcast_client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    #s.sendto(str.encode(IPAddr), ("192.168.178.255", server_port))
    broadcast_client_socket.sendto(encode_data(data), ("255.255.255.255", broadcast_port))
    broadcast_client_socket.close()

# nc -luk 10001
def listen_for_participants():
    broadcast_server_socket.bind(('', broadcast_port))
    while True:
        global participants
        new_participant, address = broadcast_server_socket.recvfrom(buffer_size)
        new_participant = decode_data(new_participant)
        if not (new_participant in participants):
            participants.append(new_participant)
            participants = sort_participants(participants)
            print(participants)
            neighbour = get_neighbour(participants, client_id)
            info_client_socket.connect((neighbour['ip'], info_port))
            data = {
                "participants": participants
            }
            info_client_socket.sendall(encode_data(data))
            info_client_socket.close()

#-------------------------------------------------------------------------------------------------------





def listen_for_info():
    global participants
    info_server_socket.bind(('', info_port))
    info_server_socket.listen(1)
    conn, addr = info_server_socket.accept()
    while True:
        try:
            data = conn.recv(buffer_size)

            if not data: break

            decoded_data = decode_data(data)
            print(decoded_data)
            participants = decoded_data["participants"]

        except socket.error:
            print("Error Occured.") 
            break

    conn.close()

#-------------------------------------------------------------------------------------------------------

# send chat messages 

def receive_messages():
    chat_server_socket.bind((server_address, chat_port))
    
    while True:
        data, address = chat_server_socket.recvfrom(buffer_size)
        print(f"{address[0]}: {data.decode()}" )

def send_messages():
    while True:
        msg = input()
        for participant in participants:
            if participant["ip"] != IPAddr:
                chat_client_socket.sendto(msg.encode(), (participant["ip"], chat_port))

#-------------------------------------------------------------------------------------------------------


if __name__ == '__main__':
    participants.append(participant_data)
    join_chat()
    Thread(target=listen_for_participants).start()
    Thread(target=receive_messages).start()
    Thread(target=send_messages).start()
    Thread(target=listen_for_info).start()
    print("server Running")

    print("Your Computer Name is: "+hostname)
    print("Your Computer IP Address is: "+IPAddr)

