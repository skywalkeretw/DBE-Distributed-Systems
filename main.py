
import socket
from threading import Thread, Condition
from multiprocessing import Process
import os
from uuid import uuid4
import json
import struct
import time

# Global Variables
debug_active = True
hostname=socket.gethostname()

buffer_size = 4069
is_leader = False
my_uuid = ""
my_name = ""

participants_ring = [] # list of ids: 33c76fe6-5c39-46a4-885c-1b770a6e786e
participants_list = {} # dictionary containing data about the participants

# ports
# join port broadcast
broadcast_port = 10001
# join info port 
connect_port = 10002
# multicast chat port
chat_address = '224.42.69.7'
chat_port = 10003
# info chat port
info_port = 10004


#-------------------------------------------------------------------------------------------------------

# helper functions

def debug(func, msg):
    """
    :param func: Function the debug statement is in
    :param msg: Message that should be Printed

    debug prints a message out if the debug_active variable is set to True
    """ 
    if debug_active:
        print(func, " -> ", msg)


def clear_output():
    """
    clear_output: Clear the console output
    """
    os.system('cls' if os.name == 'nt' else 'clear')

# Data encoding and decoding

def encode_data(d):
    """
    :param d: Data to encode

    encode_data encodes the data
    """ 
    return json.dumps(d).encode('utf-8')

def decode_data(d):
    """
    :param d: Data to decode

    decode_data decodes the data
    """ 
    return json.loads(d.decode('utf-8'))

def get_ip_address():
    """
    :return Comuters IP address
    
    get_ip_address Returns the IP address of the System
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        debug("get_ip_address", "Failed to get IP address")
    finally:
        s.close()
    return ip

# Create Listeners

def create_tcp_listener_socket():
    """
    :return tcp socket

    create_tcp_listener_socket Creates a TCP socket to listen to unicast messages
    """

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(get_ip_address(), 0)
    s.listen()
    return s

def create_udp_broadcast_listener_socket(timeout=None):
    """
    :param timeout: Set a timeour for the 
    
    :return UDP socket
    
    create_udp_broadcast_listener_socket: Create UDP socket for listening to broadcasted messages
    """

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    s.bind((get_ip_address(), 0))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # this is a broadcast socket
    if timeout:
        s.settimeout(timeout)
    return s

def create_udp_multicast_listener_socket(group):
    """
    :param group: Multicast ip and port 
    
    :return UDP socket
    
    create_udp_multicast_listener_socket: Create UDP socket for listening to multicasted messages
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(group)

    group = socket.inet_aton(group[0])
    mreq = struct.pack('4sL', group, socket.INADDR_ANY)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    return s

# Sender

def send_tcp_message(data, address):
    """
    :param data: data to send
    :param address: Address to send the data to

    send_tcp_message: Sends tcp messages by opening a new socket, 
    connecting to the socket, encoding the data, sending the data, and then closing the socket
    """
    transmit_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    transmit_socket.settimeout(1)
    transmit_socket.connect(address)
    transmit_socket.send(encode_data(data))
    transmit_socket.close()

def run_CMD(cmd_msg):
    cmd = cmd_msg.split(":")[1]
    """
    :param cmd_msg: Message to be split after the colon

    run_CMD splits message after colon
    """ 
    
    if cmd == "ip":
        print("> ", get_ip_address())
    elif cmd == "my_uuid":
        print(">", my_uuid)
    elif cmd == "participants_ring":
        print("> ", participants_ring)        
    elif cmd == "participants_list":
        print("> ", participants_list)
    elif cmd == "neighbour":
        print("> ", get_neighbour(participants_ring, my_uuid))
    elif cmd == "is_leader":
        print(f"> Is Leader: {is_leader}")
    elif cmd == "toggle_debug":
        global debug
        debug_active = not debug_active
        print(f"> debug is: {'active' if debug_active else 'disabled'}")
    

#-------------------------------------------------------------------------------------------------------

# Ring Functions

def form_ring(members):
    """
    :param members: Contains the members of the chatroom

    form_ring sorts the members according to IP
    """ 
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
        debug("join_chat","Create Client Socket")
        broadcast_client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) # might not be needed
        data = {
            "name": my_name,
            "ipaddress": IPAddr
        }
        broadcast_client_socket.sendto(encode_data(data), ("255.255.255.255", broadcast_port))
    finally:
        debug("join_chat","Close Broadcast Socket")
        broadcast_client_socket.close()
        
    joined = False
    try:
        debug("join_chat","Listen for uuid")
        confirm_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        confirm_server_socket.settimeout(5)
        confirm_server_socket.bind((IPAddr, connect_port))
        debug("join_chat","bind successfull")
        confirm_server_socket.listen()
        debug("join_chat","listen successfull")
        conn, addr = confirm_server_socket.accept()
        debug("join_chat","Connection from: " + str(addr))
        debug("join_chat","accecpt succesfull")
     
        debug("join_chat",f"Connected by {addr}")
        data_encoded = conn.recv(buffer_size)
        if data_encoded:
            joined = True
            data = decode_data(data_encoded)
            my_uuid = data["uuid"]
            participants_ring = data["participants_ring"]
            participants_list = data["participants_list"]        

    except socket.error:
        if not joined:
            debug("join_chat","Timeout !!!")
            print("Leader because first participant")
            is_leader = True
            my_uuid = str(uuid4())
            participants_ring.append(my_uuid)
            participants_list[my_uuid] = {
                "name": my_name,
                "ipaddress": IPAddr,
                "is_leader": is_leader
            }
        else:
            debug("join_chat","Timeout join true")
        

    finally:
        confirm_server_socket.close()
    
    
def listen_for_participants():
    global is_leader
    global my_uuid
    global participants_ring
    global participants_list
    try:
        debug("listen_for_participants", "Start Broadcast Listener")
        broadcast_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # broadcast_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        #broadcast_server_socket.bind(("255.255.255.255", broadcast_port))
        broadcast_server_socket.bind(('', broadcast_port))
        print("Is Leader:", is_leader)
        while True:
            if is_leader:
                debug("listen_for_participants", "Listening for new Participants")
                try:
                    # ipaddress, username, 
                    data_encoded, address = broadcast_server_socket.recvfrom(buffer_size)
                    data = decode_data(data_encoded)
                    debug("listen_for_participants", data)
                    debug("listen_for_participants", f"Name: {data['name']} ipaddress: {data['ipaddress']}")

                    if address and data and address[0] != IPAddr and data['ipaddress'] != IPAddr and data['ipaddress'] == address[0]:
                        debug("listen_for_participants", "Checks for IP OK")
                        try:
                            confirm_client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            debug("listen_for_participants","Create TCP Socket")
                            confirm_client_socket.connect((data['ipaddress'], connect_port))
                            debug("listen_for_participants",f"connection to {data['ipaddress']} succesfull")
                            
                            uuid =str(uuid4())
                            participants_ring.append(uuid)
                            participants_list[uuid] = {
                                "name": data["name"],
                                "ipaddress": data['ipaddress'],
                                "is_leader": False
                            }

                            chat_data = {
                                "uuid": uuid,
                                "participants_ring": participants_ring,
                                "participants_list": participants_list
                            }
                            status = confirm_client_socket.send(encode_data(chat_data))
                            debug("listen_for_participants", f"connection return status: {status}")
                            confirm_client_socket.close()
                        except socket.error:
                            print("Error Occured tcp.") 

                except socket.error:
                    print("Error Occured.") 
                    break

    except socket.error:
        print("Error")
    finally:
        broadcast_server_socket.close()
        
#-------------------------------------------------------------------------------------------------------

# chat

def receive_messages():
    try:
        chat_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        chat_server_socket.bind((chat_address, chat_port))
        
        # Tell the operating system to add the socket to the multicast group
        # on all interfaces.
        group = socket.inet_aton(chat_address)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        chat_server_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        while True:
            try:
                data, address = chat_server_socket.recvfrom(1024)
                decoded_data = decode_data(data)
                print(f'{address[0]}: {decoded_data["message"]}' )

            except socket.error:
                    print("Error Occured.") 
                    break

    finally:
        chat_server_socket.close()


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

# Heart Beat / info ring

def send_heartbeat():
    while True:
        debug("send_info", "Connect to neigbour to send info")
        try:
            debug("send_info","Create TCP Socket")
            info_client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            debug("send_info","Get neigbour")
            neighbour = get_neighbour(participants_ring, my_uuid)
            
            debug("send_info","Get Info abour neigbour")
            neighbour_data = participants_list[neighbour]
            
            debug("send_info", f"Connect to neighbour {neighbour_data['ipaddress']}")
            info_client_socket.connect((neighbour_data["ipaddress"], info_port))
            

            info_data = {
                "uuid": uuid,
                "participants_ring": participants_ring,
                "participants_list": participants_list
            }
            status = info_client_socket.send(encode_data(info_data))
            debug("listen_for_participants", f"connection return status: {status}")

        except socket.error:
            print("Error Occured info tcp.")
        finally:
            info_client_socket.close()

def receive_heartbeat():
    debug("receive_heartbeat", "")
    try:
        info_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        confirm_server_socket.settimeout(5)
        confirm_server_socket.bind((IPAddr, connect_port))
        debug("join_chat","bind successfull")
        confirm_server_socket.listen()
        debug("join_chat","listen successfull")
        conn, addr = confirm_server_socket.accept()
        debug("join_chat","Connection from: " + str(addr))
        debug("join_chat","accecpt succesfull")
     
        debug("join_chat",f"Connected by {addr}")
        data_encoded = conn.recv(buffer_size)
        if data_encoded:
            joined = True
            data = decode_data(data_encoded)
            my_uuid = data["uuid"]
            participants_ring = data["participants_ring"]
            participants_list = data["participants_list"]    
    
    except socket.error:
        if not joined:
            debug("join_chat","Timeout !!!")
            print("Leader because first participant")
            is_leader = True
            my_uuid = str(uuid4())
            participants_ring.append(my_uuid)
            participants_list[my_uuid] = {
                "name": my_name,
                "ipaddress": IPAddr,
                "is_leader": is_leader
            }    



#-------------------------------------------------------------------------------------------------------

# Main Function
if __name__ == '__main__':
    print("Enter username: ")
    my_name = input()
    print("Your Computer Name is: "+hostname)
    print("Your Computer IP Address is: "+IPAddr)
    # participants.append(participant_data)
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

