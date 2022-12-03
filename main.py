
import socket
from threading import Thread
from multiprocessing import Process
import os

hostname=socket.gethostname()
IPAddr=socket.gethostbyname(socket.gethostname()+'.')

server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

server_address = IPAddr #'127.0.0.1'
client_address = '192.168.178.30'
server_port = 10001

buffer_size = 4069


def receive_messages():
    server_socket.bind((server_address, server_port))
    
    while True:
        data, address = server_socket.recvfrom(buffer_size)
        print(f"{address[0]}: {data.decode()}" )

        if data:
            messge = 'Hi client nice to connect ot you'
            server_socket.sendto(str.encode(messge), address)
            print("Replied:", messge)





if __name__ == '__main__':
    Thread(target=receive_messages).start()
    print("server Running")

    print("Your Computer Name is:"+hostname)
    print("Your Computer IP Address is:"+IPAddr)

    while True:
        msg = input()
        client_socket.sendto(msg.encode(), (client_address, server_port))