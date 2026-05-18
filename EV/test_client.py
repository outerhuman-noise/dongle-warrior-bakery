import socket

SERVER_IP = '10.42.0.222'
PORT = 65432

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    try:
        s.connect((SERVER_IP, PORT))
    except ConnectionRefusedError:
        print("Could not connect. Is the server script running?")
    msg = input()
    while msg != "exit":
        s.sendall(msg.encode("utf-8"))
        data = s.recv(1024)
        print(f"Server replied: {data.decode()}")
        msg = input()

