import socket, json

hostname = socket.gethostname() # dongle-rpx with x being 1-7
with open(f"config/{hostname}.json") as f:
    config = json.load(f)

