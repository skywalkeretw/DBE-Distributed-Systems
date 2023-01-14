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
# Set debug mode boolean
debug_active = True

# By changing the port numbers, there can be more than one chat on a network
BROADCAST_PORT = 10001
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
neighbour = None

# Flag to enable stopping the client
is_active = True


# Dict for the peer mulitcast messages
peer_multi_msgs = {}

# How many messages we want to store in the dictionaries
keep_msgs = 5

#-------------------------------------------------------------------------------------------------------

# Utils

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def debug(func, msg):
    """
    :param func: Function the debug statement is in
    :param msg: Message that should be Printed

    debug prints a message out if the debug_active variable is set to True
    """ 
    if debug_active:
        print("Debug: ", func, " -> ", msg)

def create_udp_broadcast_listener_socket(timeout=None):
    """
    :param timeout: Set a timeout for the 
    
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

    if group == MG.PEER:
        if not len_other_peers:  # If there are no other servers, don't bother transmitting
            return
        expected_responses = len_other_peers
        send_to = 'peers'
        multi_msgs = peer_multi_msgs
    else:
        raise ValueError('Invalid multicast group')
     
    print(f'Sending multicast command {command} to {send_to}')

    # Create the socket
    m_sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    m_sender_socket.settimeout(0.2)
    m_sender_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

    responses = 0

    try:
        # Send message to the multicast group
        message_bytes = encode_message(command, my_address, contents)
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
        if group == MG.PEER and responses < expected_responses:
            ping_peers()

    if len(multi_msgs) > keep_msgs:
        multi_msgs.pop(next(iter(multi_msgs)))

def message_to_peers(command, contents=''):
    multicast_transmit_message(command, contents, MG.PEER)


def ping_peers(peer_to_ping=None):
    """
    ping_peers: If a specific client is provided, ping that client
    Otherwise ping all clients
    """
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

def tcp_msg_to_peers(command, contents=''):
    """
    tcp_msg_to_peers: Sends message to all peer members
     """
    global peers
    for peers in [p for p in peers if p != my_address]:
        try:
            tcp_transmit_message(command, contents, peers)
        except (ConnectionRefusedError, TimeoutError):
            print(f'Unable to send to {peers}')

# Transmits the current server and client lists from the leader to the new server
def transmit_state(address):
    state = {'peers': peers,
             'peer_multi_msgs': peer_multi_msgs}
    tcp_transmit_message('STATE', state, address)


# Receives the current server and client lists from the leader
def receive_state(state):
    global peers, peer_multi_msgs

    peers = [my_address]        # Clear the server list (except for this server)
    peers.extend(state["peers"])  # Add the received list to the servers
    peers = list(set(peers))      # Remove any duplicates
    find_neighbour()                   # Find neighbour (also takes care of sorting)

    peer_multi_msgs = state["peer_multi_msgs"]

def command(message, cmd=False):
    """
    :param message:

    command: 
    """

    if cmd:
        cmd = message.split(":")[1]
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
            if is_leader:
                print(f"> You are Leader")
        elif cmd == "toggle_debug":
            global debug
            debug_active = not debug_active
            print(f"> debug is: {'active' if debug_active else 'disabled'}")
    else:
        #print(f"Server Command: {message}")
        match message:
            # Sends the chat message to all clients
            # The client is responsible for not printing messages it originally sent
            case {'command': 'CHAT', 'sender': sender, 'contents': contents}:
                debug("command", f"{sender}: {contents}")
                print(f"{sender[0]} : {contents}")
            # Add the provided node to this server's list
            # If the request came from the node to be added inform the other servers
            # If the node is a server, send it the server and client lists
            case {'command': 'JOIN',
                    'contents': {'node_type': node_type, 'inform_others': inform_others, 'address': address}}:
                if node_type == 'peer':
                    node_list = peers
                else:
                    raise ValueError(f'Tried to add invalid node type: {node_type =}')

                if inform_others:
                    message_to_peers('JOIN', format_join_quit(node_type, False, address))
                    message_to_peers('SERV', f'{address[0]} has joined the chat') # todo: check to see if needed
                    transmit_state(address)# todo: check to see if needed                    

                if address not in node_list:  # We NEVER want duplicates in our lists
                    print(f'Adding {address} to {node_type} list')
                    node_list.append(address)
                    find_neighbour()

            # Remove the provided node to this server's list
            # If the request came from the node to be removed inform the other servers
            # If the node is a client, then inform the other clients
            case {'command': 'QUIT',
                    'contents': {'node_type': node_type, 'inform_others': inform_others, 'address': address}}:
                if node_type == 'peer':
                    node_list = peers
                else:
                    raise ValueError(f'Tried to remove invalid node type: {node_type =}')

                if inform_others:
                    message_to_peers('QUIT', format_join_quit(node_type, False, address))
                try:
                    print(f'Removing {address} from {node_type} list')
                    node_list.remove(address)
                    find_neighbour()
                        
                except ValueError:
                    print(f'{address} was not in {node_type} list')
            # Calls a function to import the current state from the leader
            # This is split of for readability and to keep global overwriting of the lists out of this function
            case {'command': 'STATE', 'contents': state}:
                receive_state(state)
            # Receive a vote in the election
            # If I get a vote for myself then I've won the election. If not, then vote
            # If the leader has been elected then set the new leader
            case {'command': 'VOTE', 'contents': {'vote_for': address, 'leader_elected': leader_elected}}:
                if not leader_elected:
                    if address == my_address:
                        set_leader(my_address)
                    else:
                        vote(address)
                else:
                    if address != my_address:
                        set_leader(address)
                        tcp_transmit_message('VOTE', {'vote_for': address, 'leader_elected': True}, neighbour)
            # Replies with the requested message to the requesting server
            case {'command': 'MSG', 'contents': {'list': list_type}, 'sender': address}:
                if list_type == 'peer':
                    multi_msgs = peer_multi_msgs
                else:
                    ValueError(f'Message requested from invalid list, {list_type =}')

                message = multi_msgs[0]
                print(f'{message =}')
                tcp_transmit_message(message['command'], message['contents'], address)
            # Either shutdown just this server (for testing leader election)
            # Or shutdown the whole chatroom
            case {'command': 'DOWN', 'contents': inform_others}:
                if inform_others:
                    tcp_msg_to_peers('DOWN')
                print(f'Shutting down at {my_address}')
                global is_active
                is_active = False

def set_leader(address):
    """
    set_leader: 
    """
    global leader_address, is_leader, is_voting
    leader_address = address
    is_leader = leader_address == my_address
    is_voting = False
    if is_leader:
        print('I am the leader')
        message_to_peers('LEAD')
        if neighbour:
            tcp_transmit_message('VOTE', {'vote_for': my_address, 'leader_elected': True}, neighbour)
    else:
        print(f'The leader is {leader_address}')

def find_neighbour():
    """
    find_neighbour: Figuring out who is our neighbour 
    Our neighbour is the server with the next highest address
    The neighbourus are used for crash fault tolerance and for voting
    """
    global neighbour
    length = len(peers)
    if length == 1:
        neighbour = None
        print('I have no neighbour')
        return
    peers.sort()
    index = peers.index(my_address)
    neighbour = peers[0] if index + 1 == length else peers[index + 1]
    print(f'My neighbour is {neighbour}') 


def vote(address):
    """
    :param address: Address to Vote for (vote for myself my_address)

    vote: starts voting by setting is_voting to true and sending a vote to neighbour
    ff we're the only peer, we win the vote automatically
    if we're the first peer to vote, this will start the whole election
    and we just vote for ourself
    otherwise, we vote for the max out of our address and the vote we received
    """
    if not neighbour:
        set_leader(my_address)
        return
    global is_voting
    vote_for = max(address, my_address)
    if vote_for != my_address or not is_voting:
        tcp_transmit_message('VOTE', {'vote_for': vote_for, 'leader_elected': False}, neighbour)
    is_voting = True

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


def parse_multicast(message, group):
    if group == MG.PEER:
        command(message)
    else:
        raise ValueError(f'Invalid multicast group, {group =}')

# Data Functions

def encode_message(command, sender, contents=''):
    """
    encode_message
    """
    message_dict = {'command': command, 'sender': sender, 'contents': contents}
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
                print("Peers: ", peers) # todo: remove when finshed debuging
                # Respond with the response code, the IP we're responding to, and the the port we're listening with
                response_message = f'{RESPONSE_CODE}_{address[0]}_{my_address[1]}'
                print(response_message)
                listener_socket.sendto(str.encode(response_message), address)

    print('Broadcast listener closing')
    listener_socket.close()
    sys.exit(0)

def tcp_listener():
    """
    tcp_listener:
    Function to listen for tcp (unicast) messages
    passes valid commands to command
    """
    tcp_listener_socket.settimeout(2)
    while is_active:
        try:
            client, address = tcp_listener_socket.accept()
        except TimeoutError:
            pass
        else:
            message = decode_message(client.recv(BUFFER_SIZE))
            if message['command'] != 'PING':  # We don't print pings since that would be a lot
                print(f'Command {message["command"]} received from {message["sender"]}')
            command(message)

    print('Unicast listener closing')
    tcp_listener_socket.close()

def heartbeat():
    """
    heartbeat: Function to ping the neighbour, and respond if unable to do so
    """
    global peers
    missed_beats = 0
    while is_active:
        # find_neighbour()
        # if neighbour and neighbour != my_address:
        #     debug("heartbeat",f"missed_beats: {missed_beats} |  neighbour: {neighbour}" )
        #debug("heartbeat",f"missed_beats: {missed_beats} |  neighbour: {neighbour}" )
        if neighbour:
            try:
                tcp_transmit_message('PING', '', neighbour)
                sleep(0.2)
            except (ConnectionRefusedError, TimeoutError):
                missed_beats += 1
            else:
                missed_beats = 0
            if missed_beats > 4:                                                         # Once 5 beats have been missed
                print(f'{missed_beats} failed pings to neighbour, remove {neighbour}')     # print to console
                # remove the missing server
                peers.remove(neighbour)                                            
                missed_beats = 0                                                         # reset the count
                tcp_msg_to_peers('QUIT', format_join_quit('peer', False, neighbour))     # inform the others
                find_neighbour()                                                          # find a new neighbour
                #check if neighbour was leader if the neighbour was leader
                debug("heartbeat", f"neighbour: {neighbour} leader_address: {leader_address}")
                neighbour_was_leader = neighbour == leader_address
                debug("heartbeat", f"{neighbour_was_leader}")
                if neighbour_was_leader or not neighbour:                                                  
                    print('Previous neighbour was leader, starting election')             # print to console
                    vote(my_address)                                                               # start an election

    print('Heartbeat thread closing')
    sys.exit(0)

# Listens for multicasted messages
def multicast_listener(group):
    #todo: match check if client is ok
    if group == MG.PEER:
            name = 'peer'
            multi_msgs = peer_multi_msgs
    else:
        raise ValueError('Invalid multicast group')

    # Create the socket
    m_listener_socket = create_udp_multicast_listener_socket(group)
    m_listener_socket.settimeout(2)

    while is_active:
        try:
            data, address = m_listener_socket.recvfrom(BUFFER_SIZE)
        except TimeoutError:
            pass
        else:
            message = decode_message(data)
            # If we've picked up our own message
            # Or the message has a lower clock than the next expected message
            # Ignore it
            # debug("multicast_listener", f"message: {message}")
            # if message['sender'] == my_address or message['clock'][0] <= clock[0]:
            #     continue
            # debug("multicast_listener", f"address: {address}")
            # print(f'Listener {name} received multicast command {message["command"]} from {message["sender"]}')
            # m_listener_socket.sendto(b'ack', message["sender"])
            command(message)
            if len(multi_msgs) > keep_msgs:
                multi_msgs.pop(next(iter(multi_msgs)))
            parse_multicast(message, group)

    print(f'Multicast listener {name} closing')
    m_listener_socket.close()
    sys.exit(0)

def transmit_messages():
    """
    transmit_message: Function to handle sending messages to the server
    """
    while is_active:
        message = input('\rYou: ')

        # This clears the just entered message from the chat using escape characters
        # Basic idea from here:
        # https://stackoverflow.com/questions/44565704/how-to-clear-only-last-one-line-in-python-output-console
        print(f'\033[A{" " * (len("You: " + message))}\033[A')

        # If the flag has been changed while waiting for input, we exit
        if not is_active:
            sys.exit(0)

        # Send message
        if len(message) > BUFFER_SIZE / 10:
            print('Message is too long')
        elif len(message) == 0:
            continue
        elif message.startswith("cmd:"):
            # client comand edit
            command(message, True)
        else:
            message_to_peers('CHAT', message)
#-------------------------------------------------------------------------------------------------------

# Create TCP socket for listening to unicast messages
# The address tuple of this socket is the unique identifier for the server
tcp_listener_socket = create_tcp_listener_socket()
my_address = tcp_listener_socket.getsockname() # to-do: rename to own address or peer_address

# Lists for connected clients and servers
peers = [my_address]  # Server list starts with this server in it

# Main Function
if __name__ == '__main__':
    # Server
    # Join Peer ring
    startup_broadcast()
    Thread(target=broadcast_listener).start()

    Thread(target=tcp_listener).start()
    Thread(target=heartbeat).start()

    Thread(target=multicast_listener, args=(MG.PEER,)).start()
    Thread(target=transmit_messages).start()
