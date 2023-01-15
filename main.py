# Imports
import socket
from threading import Thread
import os
import struct
from time import sleep
import sys
import ast
#-------------------------------------------------------------------------------------------------------
# Set debug mode boolean used by debug function
debug_active = False

# By changing the port numbers, there can be more than one chat on a network
BROADCAST_PORT = 10001
MULTICAST_PORT = 10002

# Size of Buffer for messages
BUFFER_SIZE = 4096

# Random code to broadcast and respond / listen for to filter out other network traffic
BROADCAST_CODE = 'mgay2su4peecmsreducv7vaez8ceacnc'
RESPONSE_CODE = 'xe3uyyqpvtwv234hrgsarcwjkbev8ywy'

# Number of broadcasts made by a peer at startup
JOIN_BROADCAST_ATTEMPTS = 5


# Addresses for multicast group
# Block 224.3.0.64-224.3.255.255 is all unassigned
class MG:
    PEER = ('224.3.250.250', MULTICAST_PORT)

# Variables for leadership and voting
leader_address = None
is_leader = False
is_voting = False
neighbour = None

# Flag to enable stopping the system
is_active = True

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


#-------------------------------------------------------------------------------------------------------

# Utils

def clear_console():
    """
    clear_console: Clears the console output
    """
    os.system('cls' if os.name == 'nt' else 'clear')

def debug(func, msg):
    """
    :param func: Function the debug statement is in
    :param msg: Message that should be Printed

    debug: prints a message out if the debug_active variable is set to True
    """ 
    if debug_active:
        print(f"{bcolors.WARNING}Debug:{bcolors.ENDC} ", func, " -> ", msg)

def out_cmd(msg):
    """
    :param msg: Message that should be Printed

    out_cmd: prints a message in specfic color
    """ 
    print(f"{bcolors.OKBLUE}> {msg}{bcolors.ENDC}")

def out_info(msg):
    """
    :param msg: Message that should be Printed

    out_cmd: prints a message in specfic color
    """ 
    print(f"{bcolors.OKCYAN}{msg}{bcolors.ENDC}")


def info_help():
    """
    info_help: prints the valid user commands
    """
    out_cmd("cmd:clear => Clears the Console")
    out_cmd("cmd:ip => Shows you your IP Address")
    out_cmd("cmd:ports => Get Broadcast Port and Multicast Port")
    out_cmd("cmd:peers => Shows the list of particpating peers")
    out_cmd("cmd:neighbour => Shows you your neighbour")
    out_cmd("cmd:is_leader => Shows you if you are a leader or a participant")
    out_cmd("cmd:toggle_debug => Activates the debug mode")
    
#-------------------------------------------------------------------------------------------------------

# Socket Listener

def create_udp_broadcast_listener_socket(timeout=None):
    """
    :param timeout: Set a timeout for the 
    
    :return UDP socket
    
    create_udp_broadcast_listener_socket: Create UDP socket for listening to broadcasted messages
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
    s.bind((get_ip_address(), 0))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if timeout:
        s.settimeout(timeout)
    return s

def create_udp_multicast_listener_socket(group):
    """
    :param group: Multicast ip and port as tuple
    
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

#-------------------------------------------------------------------------------------------------------

# Socket Send

def tcp_transmit_message(command, contents, address):
    """
    :param command: Action that should be executed (CHAT, JOIN, PING...)
    :param contents: Data to be sent
    :param address: Address tupple to send the message to

    tcp_transmit_message: Send TCP Message to peer
    """
    if command != 'PING':
        debug("tcp_transmit_message", f'Sending command {command} to {address}')
    message_bytes = encode_message(command, my_address, contents)
    transmit_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    transmit_socket.settimeout(1)
    transmit_socket.connect(address)
    transmit_socket.send(message_bytes)
    transmit_socket.close()


def multicast_transmit_message(command, contents='', group=MG.PEER):
    """
    :param command: Action that should be executed (CHAT, JOIN, PING...)
    :param contents: Data to be sent
    :param group:                   Address tupple to send the message to the Multicast Group

    multicast_transmit_message: transmits multicast messages
    """
    if group == MG.PEER:
        # If there are no other peers, no need to send message
        if not (len(peers) - 1):  
            return
    else:
        raise ValueError('Invalid multicast group')
     
    debug("multicast_transmit_message", f'Sending multicast command {command} send message {contents} to peers: {peers}')

    m_sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    m_sender_socket.settimeout(0.2)
    m_sender_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

    try:
        message_bytes = encode_message(command, my_address, contents)
        m_sender_socket.sendto(message_bytes, group)
    finally:
        m_sender_socket.close()

def tcp_msg_to_peers(command, contents=''):
    """
    :param command: Action that should be executed (CHAT, JOIN, PING...)
    :param contents: Data to be sent
    
    tcp_msg_to_peers: Sends tcp message to all peers
    """
    for target_peer in [p for p in peers if p != my_address]:
        try:
            debug("tcp_msg_to_peers", f"peers: {peers}")
            debug("tcp_msg_to_peers", f"target_peers: {peers}")
            tcp_transmit_message(command, contents, target_peer)
        except (ConnectionRefusedError, TimeoutError):
            debug("tcp_msg_to_peers", f'Unable to send to {peers}')

#-------------------------------------------------------------------------------------------------------

# Command Function

def command(message, cmd=False):
    """
    :param message:
    :param cmd:

    command: Run diffrent commands depending on the 
    """
    global peers
    if cmd:
        cmd = message.split(":")[1]
        if cmd == "ip":
            out_cmd(f"Your IP: {get_ip_address()}")
        elif cmd == "ports":
            out_cmd(f"Broadcast Port: {BROADCAST_PORT},  Multicast Port: {MULTICAST_PORT}")
        elif cmd == "clear":
            clear_console()
        elif cmd == "neighbour":
            out_cmd(f"Your Neighbour: {find_neighbour()}")
        elif cmd == "is_leader":
            out_cmd(f"You are Leader" if is_leader else f"You are Participant")
        elif cmd == "peers":
            out_cmd(f"List of peers: {peers}")
        elif cmd == "toggle_debug":
            global debug_active
            debug_active = not debug_active
            out_cmd(f"debug is: {'active' if debug_active else 'disabled'}")
        elif cmd == "debug":
            out_cmd(f"debug is: {'active' if debug_active else 'disabled'}")
        elif cmd == "help":
            info_help()
        else:
            out_cmd(f"Your command is invalid. Use 1 of the following Commands:")
            info_help()
    else:
        match message:

            case {'command': 'CHAT', 'sender': sender, 'contents': contents}:
                print(f"({sender[0]}): {contents}")
            # Add the provided node to this peers list
            # If the request came from the node to be added inform the other peers
            # send it to the peer lists
            case {'command': 'JOIN', 'contents': {'node_type': node_type, 'inform_others': inform_others, 'address': address}}:
                if node_type != 'peer':
                    raise ValueError(f'Tried to add invalid node type: {node_type =}')

                if inform_others:
                    # return Peer list
                    tcp_transmit_message('STATE', {'peers': peers}, address)  
                    # inform Peers about new Peer
                    multicast_transmit_message('JOIN', format_join_quit(node_type, False, address))            

                if address not in peers:
                    debug("not in",f'Adding {address} to {node_type} list')
                    out_info(f"({address[0]}): Hello I Joined the Chat")
                    peers.append(address)
                    find_neighbour()

            # Remove the provided node from the peer list
            # If the request came from the node to be removed inform the other peers
            # If the node is a client, then inform the other clients
            case {'command': 'QUIT', 'contents': {'node_type': node_type, 'inform_others': inform_others, 'address': address}}:
                if node_type != 'peer':
                    raise ValueError(f'Tried to remove invalid node type: {node_type =}')

                if inform_others:
                    multicast_transmit_message('QUIT', format_join_quit(node_type, False, address))
                try:
                    debug("command", f'Removing {address} from {node_type} list')
                    out_info(f"({address[0]}): Left the Chat")
                    peers.remove(address)
                    find_neighbour()
                        
                except ValueError:
                    debug("command", f'{address} was not in {node_type} list')
            # Calls a function to import the current state from the leader
            # This is split of for readability and to keep global overwriting of the lists out of this function
            case {'command': 'STATE', 'contents': state}:
                # Clear the peers list (except for this peer)
                peers = [my_address]
                debug("command", f"STATE peers: {peers}")
                # Add the received list to the peers
                peers.extend(state["peers"])
                debug("command", f"STATE peers: {peers}")
                #Remove any duplicates from the peers
                peers = list(set(peers))
                debug("command", f"STATE peers: {peers}")
                find_neighbour()
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

def set_leader(address):
    """
    :param address:

    set_leader: 
    """
    global leader_address, is_leader, is_voting
    leader_address = address
    is_leader = leader_address == my_address
    is_voting = False
    if is_leader:
        debug("set_leader", 'I am the leader')
        multicast_transmit_message('LEAD')
        if neighbour:
            tcp_transmit_message('VOTE', {'vote_for': my_address, 'leader_elected': True}, neighbour)
    else:
        debug("set_leader",f'The leader is {leader_address}')

def find_neighbour():
    """
    find_neighbour: Figuring out who is our neighbour 
    Our neighbour is the peer with the next highest address
    The neighbourus are used for crash fault tolerance and for voting
    """
    global neighbour
    length = len(peers)
    if length == 1:
        neighbour = None
        debug("find_neighbour", 'I have no neighbour')
        return
    debug("find_neighbour", f"Peers: {peers}")
    peers.sort()
    index = peers.index(my_address)
    neighbour = peers[0] if index + 1 == length else peers[index + 1]
    debug("neighbour", f'My neighbour is {neighbour}') 


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
    :return Computers IP address
    
    get_ip_address Returns the IP address of the System
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        debug("get_ip_address","Failed to get IP address")
    finally:
        s.close()
    return ip
        
#-------------------------------------------------------------------------------------------------------        

# Data Functions

def encode_message(command, sender, contents=''):
    """
    :param command:
    :param sender:
    :param contents:

    encode_message
    """
    message_dict = {'command': command, 'sender': sender, 'contents': contents}
    return repr(message_dict).encode()

def decode_message(message):
    """
    :param message:

    decode_message
    """
    return ast.literal_eval(message.decode())

def format_join_quit(node_type, inform_others, address):
    """
    :param node_type:
    :param inform_others:
    :param address:
    
    format_join_quit returns 
    """
    return {'node_type': node_type, 'inform_others': inform_others, 'address': address}

#-------------------------------------------------------------------------------------------------------

# Peer Functions

def startup_broadcast():
    """
    startup_broadcast Broadcasts looking for another active Peer acting as Leader 

    """
    # Create UDP Broadcast socket
    broadcast_socket = create_udp_broadcast_listener_socket(timeout=1)

    got_response = False

    # 5 attempts are made to find another leader
    # After this, the peer assumes it is the only one and considers itself leader
    for i in range(0, JOIN_BROADCAST_ATTEMPTS):
        #Broadcast message looking for a leader
        broadcast_socket.sendto(BROADCAST_CODE.encode(), ('<broadcast>', BROADCAST_PORT))
        debug("startup_broadcast", "Looking for Leader")

        # Wait for a response packet. If no packet has been received in 1 second, broadcast again
        try:
            data, address = broadcast_socket.recvfrom(BUFFER_SIZE)
            # RandomResponseCode_IPAddressFromLeader
            if data.startswith(f'{RESPONSE_CODE}_{my_address[0]}'.encode()):
                
                debug("startup_broadcast", f"Found Leader at {address[0]}")
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
        debug("startup_broadcast", 'No other Leader found')
        set_leader(my_address)

def broadcast_listener():
    """
    broadcast_listener
    Function to listen for broadcasts from peers and respond when a broadcast is heard
    Only the leader responds to broadcasts
    """
    if leader_address[0] == get_ip_address() :
        debug("broadcast_listener", f'Leader up and running at -> {my_address[0]}:{my_address[1]}')

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
                debug("broadcast_listener",f'Received broadcast from {address[0]}, replying with response code')
                debug("broadcast_listener",f"Peers: {peers}",) # todo: remove when finshed debuging
                # Respond with the response code, the IP we're responding to, and the the port we're listening with
                response_message = f'{RESPONSE_CODE}_{address[0]}_{my_address[1]}'
                debug("broadcast_listener",response_message)
                listener_socket.sendto(str.encode(response_message), address)

    debug("broadcast_listener", 'Broadcast listener closing')
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
            if message['command'] != 'PING':
                debug("tcp_listener",f'Command {message["command"]} received from {message["sender"]}')
            command(message)

    debug("tcp_listener", 'Unicast listener closing')
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
            if missed_beats > 4:
                debug("heartbeat", f'{missed_beats} failed pings to neighbour, remove {neighbour}')       
                # remove the missing peer
                debug("heartbeat", f"Peers :{peers}")
                peers.remove(neighbour)
                debug("heartbeat", f"Peers {peers}")                                   
                missed_beats = 0 
                debug("heartbeat", f"Peers {peers}")                                   
                tcp_msg_to_peers('QUIT', format_join_quit('peer', False, neighbour))         # inform the others
                previous_neighbour = neighbour
                out_info(f"({previous_neighbour[0]}): Left the Chat")
                find_neighbour()                                                             
                #check if neighbour was leader if the neighbour was leader
                debug("heartbeat", f"neighbour: {neighbour} leader_address: {leader_address}")
                neighbour_was_leader = previous_neighbour == leader_address
                debug("heartbeat", f"neighbour_was_leader: {neighbour_was_leader} previous_neighbour: {previous_neighbour}")
                if neighbour_was_leader or not neighbour:                                                  
                    debug("heartbeat",'Previous neighbour was leader, starting election')
                    vote(my_address)

    debug("heartbeat", 'Heartbeat thread closing')
    sys.exit(0)

def ping_peers(peer_to_ping=None):
    """
    :param peer_to_ping: single peer to ping
    
    ping_peers: If a specific client is provided, ping that client 
    Otherwise ping all clients or just one
    """
    if peer_to_ping:
        to_ping = [peer_to_ping]
    else:
        to_ping = peers

    for peer in to_ping:
        try:
            tcp_transmit_message('PING', '', peer)
        except (ConnectionRefusedError, TimeoutError):  
            # If we can't connect to a peer, then drop it
            debug(f'Failed send to {peer} removeing from list')
            debug(f'Peers: {peers}')
            try:
                peers.remove(peers)
                multicast_transmit_message('QUIT', format_join_quit('client', False, peer))
                # multicast_transmit_message('SERV', f'{client[0]} is unreachable')
            except ValueError:
                debug("ping_peers", f'{peer} was not in peers')

def multicast_listener():
    """
    :param group:
    multicast_listener: Listens for multicasted messages
    """
    # Create the socket
    m_listener_socket = create_udp_multicast_listener_socket(MG.PEER)
    m_listener_socket.settimeout(2)

    while is_active:
        try:
            data, address = m_listener_socket.recvfrom(BUFFER_SIZE)
        except TimeoutError:
            pass
        else:
            debug("multicast_listener", f"address: {address} my_address {my_address}")
            if address[0] != my_address[0]:
                message = decode_message(data)
                command(message)

    debug("multicast_listener", f'Multicast listener peer closing')
    m_listener_socket.close()
    sys.exit(0)

def transmit_messages():
    """
    transmit_message: Function to handle sending messages to the peers
    """
    while is_active:
        message = input()

        # This clears the just entered message from the chat using escape characters
        # Basic idea from here:
        # https://stackoverflow.com/questions/44565704/how-to-clear-only-last-one-line-in-python-output-console
        print(f'\033[A{" " * (len(message))}\033[A')
        print(f"{bcolors.OKGREEN}({my_address[0]}){bcolors.ENDC}: {message}")
        # If the flag has been changed while waiting for input, we exit
        if not is_active:
            sys.exit(0)

        # Send message
        if len(message) > BUFFER_SIZE / 10:
            debug("transmit_messages", f'Message is too long {len(message)}')
        elif len(message) == 0:
            continue
        elif message.startswith("cmd:"):
            # client comand edit
            command(message, True)
        else:
            debug("transmit_messages", f"message: {message}")
            multicast_transmit_message('CHAT', message)
#-------------------------------------------------------------------------------------------------------

# Create TCP socket for listening to unicast messages
# The address tuple of this socket is the unique identifier for the leader
tcp_listener_socket = create_tcp_listener_socket()
my_address = tcp_listener_socket.getsockname() # to-do: rename to own address or peer_address

# Lists for connected peers
peers = [my_address]  # Peers list starts with this peer in it

# Main Function
if __name__ == '__main__':
    # Join Peer ring
    # Broadcast communication
    startup_broadcast()
    out_info(f"Hello {my_address[0]} Welcome to the Chat")
    out_info(f"Use `cmd:help` for more information")
    if my_address[0] != leader_address[0] and len(peers) == 1:
        out_info(f"Type Your message:")
    else:
        out_info(f"You are alone :(")
    Thread(target=broadcast_listener).start()

    # TCP Communication
    Thread(target=tcp_listener).start()
    Thread(target=heartbeat).start()

    # Message Multicast communication
    Thread(target=multicast_listener).start()
    Thread(target=transmit_messages).start()

#-------------------------------------------------------------------------------------------------------