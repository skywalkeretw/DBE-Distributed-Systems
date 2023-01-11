
import socket
from threading import Thread, Condition
from multiprocessing import Process
import os
from uuid import uuid4
import json
import struct
import time

# Global Variables
hostname=socket.gethostname()
IPAddr=socket.gethostbyname(socket.gethostname()+'.')
buffer_size = 4069
is_leader = False
my_uuid = ""
my_name = ""

participants_ring = [] # list of ids: 33c76fe6-5c39-46a4-885c-1b770a6e786e
participants_list = {} # dictionary containing data about the participants

# ports
broadcast_port = 10001
connect_port = 10002



#chat sockets
chat_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
chat_address = '224.42.69.7'
chat_port = 10002
#info sockets TCP
info_server_socket, info_client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) , socket.socket(socket.AF_INET, socket.SOCK_STREAM)
info_port = 10003


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
    elif cmd == "participants_ring":
        print("> ", participants_ring)        
    elif cmd == "participants_list":
        print("> ", participants_list)
    elif cmd == "neighbour":
        print("> ", get_neighbour(participants_ring, my_uuid))
    elif cmd == "is_leader":
        print(f"> Is Leader: {is_leader}")
    

#-------------------------------------------------------------------------------------------------------

# Ring Functions

def form_ring(members):
    sorted_binary_ring = sorted([socket.inet_aton(member) for member in members])
    sorted_ip_ring = [socket.inet_ntoa(node) for node in sorted_binary_ring]
    return sorted_ip_ring

def get_neighbour(ring, current_node_ip, direction='left'):
    current_node_index = ring.index(current_node_ip) if current_node_ip in ring else -1
    if current_node_index != -1:
        if direction == 'left':
            if current_node_index + 1 == len(ring):
                return ring[0]
            else:
                return ring[current_node_index + 1]
        else:
            if current_node_index == 0:
                return ring[len(ring) - 1]
            else:
                return ring[current_node_index - 1]
    else:
        return None

#-------------------------------------------------------------------------------------------------------

# Broadcast to Join the chat

def join_chat():
    global is_leader
    global my_uuid
    global participants_ring
    global participants_list
    # Broadcast "I want to join the chat"
    try:
        print("Create Client Socket")
        broadcast_client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        data = {
            "name": my_name
        }
        broadcast_client_socket.sendto(encode_data(data), ("255.255.255.255", broadcast_port))
    finally:
        broadcast_client_socket.close()
        
    count = 0
    try:
        print("Listen for uuid")
        confirm_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        confirm_server_socket.settimeout(5)
        confirm_server_socket.bind((IPAddr, connect_port))
        print("bind successfull")
        confirm_server_socket.listen()
        print("listen successfull")
        conn, addr = confirm_server_socket.accept()
        print("Connection from: " + str(addr))
        print("accecpt succesfull")
     
        print(f"Connected by {addr}")
        data_encoded = conn.recv(buffer_size)
        data = decode_data(data_encoded)
        my_uuid = data["uuid"]
        participants_ring = data["participants_ring"]
        participants_list = data["participants_list"]        
    except socket.error:
        print("Timeout !!!")
        print("Leader because first participant")
        is_leader = True
        my_uuid = str(uuid4())
        participants_ring.append(my_uuid)
        participants_list[my_uuid] = {
            "name": my_name,
            "ipaddress": IPAddr,
            "is_leader": is_leader
        }
        

    finally:
        confirm_server_socket.close()
    
    
def listen_for_participants():
    global is_leader
    global my_uuid
    global participants_ring
    global participants_list
    try:
        broadcast_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        broadcast_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        broadcast_server_socket.bind(("255.255.255.255", broadcast_port))
        print()
        while True:
            if is_leader:
                try:
                    # ipaddress, username, 
                    data_encoded, address = broadcast_server_socket.recvfrom(buffer_size)
                    data = decode_data(data_encoded)
                    if address[0] != IPAddr:

                        if address:
                            try:
                                confirm_client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                confirm_client_socket.connect((address[0], connect_port))
                                print("connect succesfull")
                                uuid =str(uuid4())
                                participants_ring.append(uuid)
                                participants_list[uuid] = {
                                    "name": data["name"],
                                    "ipaddress": address[0],
                                    "is_leader": False
                                }

                                chat_data = {
                                    "uuid": uuid,
                                    "participants_ring": participants_ring,
                                    "participants_list": participants_list
                                }
                                confirm_client_socket.send(encode_data(chat_data))
                            finally:
                                confirm_client_socket.close()

                except socket.error:
                    print("Error Occured.") 
                    break

    except socket.error:
        print("Error")
    finally:
        broadcast_server_socket.close()
        
#-------------------------------------------------------------------------------------------------------


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


# Main Function
if __name__ == '__main__':
    print("Enter username: ")
    my = input()
    print("Your Computer Name is: "+hostname)
    print("Your Computer IP Address is: "+IPAddr)
    # participants.append(participant_data)
    join_chat()
    
    t_listen_for_participants = Thread(target=listen_for_participants, args=(), daemon=False)
    t_listen_for_participants.start()

    # Thread That Sends Messages 
    t_send_messages = Thread(target=send_messages, args=(), daemon=False)
    t_send_messages.start()