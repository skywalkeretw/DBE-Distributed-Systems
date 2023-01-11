
import socket
from threading import Thread, Condition
from multiprocessing import Process
import os
from uuid import uuid4
import json
import struct

hostname=socket.gethostname()
IPAddr=socket.gethostbyname(socket.gethostname()+'.')


# UDP : socket.SOCK_DGRAM
# 
# TCP : socket.SOCK_STREAM
#

# TCP flow
# Server
# s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# s.bind(address)
# s.listen()
# s.accept()
# s.recv(buffer_size)
# s.send(bytees_data)
# s.recv(buffer_size)
# s.close

# Client
# s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# s.connect(address)
# s.send(bytes)
# s.recv(buffer_size)
# s.close()

# try:
#     send encode_data
#     receve response
# finally:
#     close server
#---------------------------------------------------------------

# UDP flow
# Server
# s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# s.bind((address, port))
# s.recvfrom(buffer_size)
# s.sendto(bytees_data, address)

# Client
# s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# s.sendto(bytees_data, (address, port))
# s.recvfrom(buffer_size)
#---------------------------------------------------------------

# broadcast sockets
broadcast_server_socket, broadcast_client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) , socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
broadcast_port = 10001
#chat sockets
chat_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
chat_address = '224.42.69.7'
chat_port = 10002
#info sockets TCP
info_server_socket, info_client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) , socket.socket(socket.AF_INET, socket.SOCK_STREAM)
info_port = 10003

server_address = IPAddr #'127.0.0.1'

buffer_size = 4069
client_id = str(uuid4())

c = Condition()
participants = [] # liste mit dict

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

def run_CMD(cmd_msg):
    cmd = cmd_msg.split(":")[1]
    
    if cmd == "ip":
        print("> ", IPAddr)
    elif cmd == "participants":
        print("> ", participants)
    elif cmd == "neighbour":
        print("> ", get_neighbour(participants, client_id))

def sort_participants(participants):
    return sorted(participants, key=lambda d: d['id'])

def get_index_of_participant_id(uid):
    return next((index for (index, d) in enumerate(participants) if d["id"] == uid), -1)

def get_index_of_participant_ip(ip):
    return next((index for (index, d) in enumerate(participants) if d["ip"] == ip), -1)

def get_index_of_participant_uid_id(uid, ip):
    return next((index for (index, d) in enumerate(participants) if d["id"] == uid and d["ip"] == ip), -1)

def get_neighbour(ring, uid, direction='left'):
    current_index = get_index_of_participant_id(uid)
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
        try:
            global participants
            new_participant, address = broadcast_server_socket.recvfrom(buffer_size)
            new_participant = decode_data(new_participant)
            if not (new_participant in participants):
                c.acquire()
                participants.append(new_participant)
                participants = sort_participants(participants)
                c.notify_all()
                c.release()
                
                neighbour = get_neighbour(participants, client_id)

                #check if connection can be established to the neigbour
                try:
                    info_client_socket.connect((neighbour['ip'], info_port))
                    data = {
                        "participants": participants
                    }
                    info_client_socket.sendall(encode_data(data))
                    info_client_socket.close()

                except socket.error:
                    print("Cant Send To Neighbour") 
                    
                    c.acquire()
                    del participants[get_index_of_participant_id(neighbour["id"])]
                    participants = sort_participants(participants)
                    c.notify_all()
                    c.release()
                    # Schleife notwendig ansonsten Problem wenn 2. Nachbar auch nicht gefunden wird? 
                    neighbour = get_neighbour(participants, client_id)
                    info_client_socket.connect((neighbour['ip'], info_port))
                    data = {
                        "participants": participants
                    }
                    info_client_socket.sendall(encode_data(data))
                    info_client_socket.close()
                    

        except socket.error:
            print("Error Occured.") 
            break

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
            c.acquire()
            participants = decoded_data["participants"]
            c.notify_all()
            c.release()
            neighbour = get_neighbour(participants, client_id)
            print(neighbour)

        except socket.error:
            print("Error Occured Listening for info.") 
            break

    conn.close()

#-------------------------------------------------------------------------------------------------------

# send chat messages as multicast

def receive_messages():
    chat_server_socket.bind(('', chat_port))
    
    # Tell the operating system to add the socket to the multicast group
    # on all interfaces.
    group = socket.inet_aton(chat_address)
    mreq = struct.pack('4sL', group, socket.INADDR_ANY)
    chat_server_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    while True:
        data, address = chat_server_socket.recvfrom(1024)
        decoded_data = decode_data(data)
        print(f'{address[0]}: {decoded_data["message"]}' )



def send_messages():
    while True:
        msg = input()

        is_CMD = msg.startswith("cmd:")
        if is_CMD:
            run_CMD(msg)
        else:
            data = {
                "message": msg
            }

            # Create the datagram socket
            chat_client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            # Set the time-to-live for messages to 1 so they do not go past the
            # local network segment.
            ttl = struct.pack('b', 1)
            chat_client_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

            try:

                # Send data to the multicast group
                chat_client_socket.sendto(encode_data(data), (chat_address, chat_port))

            finally:
                chat_client_socket.close()
                



#-------------------------------------------------------------------------------------------------------

# Programm: source code for process
# Process: Unit of program execution as seen by an  OS
# Thread: Sequential flow of control within a process, Process can contain multiple threads
# Multiprocessing: concurrent execution of several programms on one machine
# Multithreading: execution of a programm with multiple threads

if __name__ == '__main__':
    print("Your Computer Name is: "+hostname)
    print("Your Computer IP Address is: "+IPAddr)
    participants.append(participant_data)
    join_chat()

    # Thread That listen for Broadcast messages with new participants
    t_listen_for_participants = Thread(target=listen_for_participants, args=(), daemon=False)
    t_listen_for_participants.start()

    # Thread that listens for incoming messages
    t_receive_messages = Thread(target=receive_messages, args=(), daemon=False)
    t_receive_messages.start()
    
    # Thread That Sends Messages 
    t_send_messages = Thread(target=send_messages, args=(), daemon=False)
    t_send_messages.start()
    
    t_listen_for_info = Thread(target=listen_for_info, args=(), daemon=False)
    t_listen_for_info.start()
    



