# Imports
import socket
from threading import Thread, Condition
from multiprocessing import Process
import os
from uuid import uuid4
import json
import struct
from time import sleep
import sys
import ast
#-------------------------------------------------------------------------------------------------------

# By changing the port numbers, there can be more than one chat on a network
BROADCAST_PORT = 10001
#ML_SERVER_PORT = 10002
#ML_CLIENT_PORT = 10003
ML_PEER_PORT = 10002
BUFFER_SIZE = 4096
# Random code to broadcast / listen for to filter out other network traffic
BROADCAST_CODE = '9310e231f20a07cb53d96b90a978163d'
# Random code to respond with
RESPONSE_CODE = 'f56ddd73d577e38c45769dcd09dc9d99'
# Number of broadcasts made by a server at startup
SERVER_BROADCAST_ATTEMPTS = 5
# Addresses for multicast groups
# Block 224.3.0.64-224.3.255.255 is all unassigned
# Choices are arbitrary for now
class MG:
    #SERVER = ('224.3.100.255', ML_SERVER_PORT)
    #CLIENT = ('224.3.200.255', ML_CLIENT_PORT)
    PEER = ('224.3.200.255', ML_PEER_PORT)

# Variables for leadership and voting
leader_address = None
is_leader = False
is_voting = False
neighbor = None

# Flag to enable stopping the client
is_active = True

# Counts for server and client multicasts
server_clock = [0]
client_clock = [0]

# Dict for the peer mulitcast messages
peer_multi_msgs = {}

# How many messages we want to store in the dictionaries
keep_msgs = 5

#-------------------------------------------------------------------------------------------------------

# Utils

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

def create_tcp_listener_socket():
    """
    :return tcp socket

    create_tcp_listener_socket Creates a TCP socket to listen to unicast messages
    """

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((get_ip_address(), 0))
    s.listen()
    return s

def tcp_transmit_message(command, contents, address):
    """
    tcp_transmit_message
    """
    if command != 'PING':
        print(f'Sending command {command} to {address}')
    message_bytes = encode_message(command, my_address, contents)
    transmit_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    transmit_socket.settimeout(1)
    transmit_socket.connect(address)
    transmit_socket.send(message_bytes)
    transmit_socket.close()


def multicast_transmit_message(command, contents, group):
    """
    multicast_transmit_message: transmits multicast messages and checks how many responses are received
    """
    len_other_peers = len(peers) - 1 # We expect responses from every other than the sender

    match group:
        case MG.PEER:
            if not len_other_peers:  # If there are no other servers, don't bother transmitting
                return
            expected_responses = len_other_peers
            send_to = 'peers'
            multi_msgs = peer_multi_msgs
            clock = server_clock
        case _:
            raise ValueError('Invalid multicast group')

    clock[0] += 1
    print(f'Sending multicast command {command} to {send_to} with clock {clock[0]}')

    # Create the socket
    m_sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    m_sender_socket.settimeout(0.2)
    m_sender_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

    responses = 0

    try:
        # Send message to the multicast group
        message_bytes = encode_message(command, my_address, contents, clock)
        m_sender_socket.sendto(message_bytes, group)

        # Look for responses from all recipients
        while True:
            try:
                data, server = m_sender_socket.recvfrom(16)
            except TimeoutError:
                break
            else:
                responses += 1
    finally:
        print(f'Received {responses} of {expected_responses} expected responses')
        m_sender_socket.close()
        if group == MG.CLIENT and responses < expected_responses:
            ping_peers()

    multi_msgs[str(clock[0])] = {'command': command, 'contents': contents}
    if len(multi_msgs) > keep_msgs:
        multi_msgs.pop(next(iter(multi_msgs)))

def message_to_peers(command, contents=''):
    multicast_transmit_message(command, contents, MG.PEER)

# If a specific client is provided, ping that client
# Otherwise ping all clients
def ping_peers(peer_to_ping=None):
    if peer_to_ping:
        to_ping = [peer_to_ping]
    else:
        to_ping = peers

    for peer in to_ping:
        try:
            tcp_transmit_message('PING', '', peer)
        except (ConnectionRefusedError, TimeoutError):  # If we can't connect to a client, then drop it
            print(f'Failed send to {peer}')
            print(f'Removing {peer} from peer')
            try:
                peers.remove(peers)
                message_to_peers('QUIT', format_join_quit('client', False, peer))
                # message_to_clients('SERV', f'{client[0]} is unreachable')
            except ValueError:
                print(f'{peer} was not in peers')


def set_leader(address):
    """
    set_leader
    """
    global leader_address, is_leader, is_voting
    leader_address = address
    is_leader = leader_address == my_address
    is_voting = False
    if is_leader:
        print('I am the leader')
        message_to_peers('LEAD')
        if neighbor:
            tcp_transmit_message('VOTE', {'vote_for': my_address, 'leader_elected': True}, neighbor)
    else:
        print(f'The leader is {leader_address}')


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
        print("Failed to get IP address")
    finally:
        s.close()
    return ip



# Data Functions

def encode_message(command, sender, contents='', clock=None):
    """
    encode_message
    """
    message_dict = {'command': command, 'sender': sender, 'contents': contents, 'clock': clock}
    return repr(message_dict).encode()

def decode_message(message):
    """

    decode_message
    """
    return ast.literal_eval(message.decode())

def format_join_quit(node_type, inform_others, address):
    """
    format_join_quit returns 
    """
    return {'node_type': node_type, 'inform_others': inform_others, 'address': address}

#-------------------------------------------------------------------------------------------------------


# Server Functions

def startup_broadcast():
    """
    startup_broadcast Broadcasts looking for another active Peer acting as Leader 

    """
    # Create UDP Broadcast socket
    broadcast_socket = create_udp_broadcast_listener_socket(timeout=1)

    got_response = False

    # 5 attempts are made to find another server
    # After this, the server assumes it is the only one and considers itself leader
    for i in range(0, SERVER_BROADCAST_ATTEMPTS):
        #Broadcast message looking for a leader
        broadcast_socket.sendto(BROADCAST_CODE.encode(), ('<broadcast>', BROADCAST_PORT))
        print("Looking for Leader")

        # Wait for a response packet. If no packet has been received in 1 second, broadcast again
        try:
            data, address = broadcast_socket.recvfrom(BUFFER_SIZE)
            # RandomResponseCode_IPAddressFromLeader
            if data.startswith(f'{RESPONSE_CODE}_{my_address[0]}'.encode()):
                
                print("Found Leader at", address[0])
                response_port = int(data.decode().split('_')[2])
                join_contents = format_join_quit('peer', True, my_address)
                tcp_transmit_message('JOIN', join_contents, (address[0], response_port))
                got_response = True
                set_leader((address[0], response_port))
                break
        except TimeoutError:
            pass

    broadcast_socket.close()
    if not got_response:
        print('No other Leader found')
        set_leader(my_address)

def broadcast_listener():
    """
    broadcast_listener
    Function to listen for broadcasts from peers and respond when a broadcast is heard
    Only the leader responds to broadcasts
    """
    if leader_address[0] == get_ip_address() :
        print(f'Leader up and running at -> {my_address[0]}:{my_address[1]}')

    listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  
    listener_socket.bind(('', BROADCAST_PORT))
    listener_socket.settimeout(2)

    while is_active:
        try:
            data, address = listener_socket.recvfrom(BUFFER_SIZE)  # wait for a packet
        except TimeoutError:
            pass
        else:
            if is_leader and data.startswith(BROADCAST_CODE.encode()):
                print(f'Received broadcast from {address[0]}, replying with response code')
                # Respond with the response code, the IP we're responding to, and the the port we're listening with
                response_message = f'{RESPONSE_CODE}_{address[0]}_{my_address[1]}'
                print(response_message)
                listener_socket.sendto(str.encode(response_message), address)

    print('Broadcast listener closing')
    listener_socket.close()
    sys.exit(0)
#-------------------------------------------------------------------------------------------------------

# Create TCP socket for listening to unicast messages
# The address tuple of this socket is the unique identifier for the server
server_socket = create_tcp_listener_socket()
my_address = server_socket.getsockname() # to-do: rename to own address or peer_address

# Lists for connected clients and servers
peers = [my_address]  # Server list starts with this server in it

# Main Function
if __name__ == '__main__':
    # Server
    # Join Peer ring
    startup_broadcast()
    Thread(target=broadcast_listener).start()

#----

    # Thread(target=tcp_listener).start()
    # Thread(target=heartbeat).start()
    
    # Thread(target=multicast_listener, args=(MG.SERVER,)).start()
    # Thread(target=multicast_listener, args=(MG.CLIENT,)).start()

    # # Client
    # clear_output()
    # #broadcast_for_server()

    # Thread(target=transmit_messages).start()
    # #Thread(target=tcp_listener).start() # fin
    # #Thread(target=multicast_listener).start()