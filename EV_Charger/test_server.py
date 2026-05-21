import socket
import signal
import sys

HOST = '10.42.0.222'
PORT = 65432

def create_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Allow port reuse immediately after the script stops
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    s.bind((HOST, PORT))
    s.listen()
    print(f"Server listening on {HOST}:{PORT}...")
    return s

def main():
    server = create_server()

    # Gracefully shut down on Ctrl+C or kill signal
    def shutdown(sig, frame):
        print("\nShutting down server...")
        server.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)   # Ctrl+C
    signal.signal(signal.SIGTERM, shutdown)  # kill command

    while True:
        conn, addr = server.accept()
        with conn:
            print(f"Connected by {addr}")
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                print(f"Received: {data.decode()}")
                conn.sendall(b"Message received!")

main()