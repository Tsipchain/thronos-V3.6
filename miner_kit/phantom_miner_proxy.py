
import socket
import time

# Configuration
SERVER_HOST = "stratum+tcp://thronos-server.up.railway.app:443"  # Corrected server host configuration
SERVER_PORT = 3333
BTC_ADDRESS = "3KUGVJ96T3JHuUrEHMeAvDKSo1zM9tD9nF"
REFERRAL = "ref123"

def main():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((SERVER_HOST, SERVER_PORT))
        print(f"[+] Connected to Thronos server at {SERVER_HOST}:{SERVER_PORT}")

        # Send the miner identification line
        s.sendall(f"btc:{BTC_ADDRESS}\n".encode())
        time.sleep(0.5)
        s.sendall(f"ref:{REFERRAL}\n".encode())

        # Keep alive (simulate idle miner connection)
        while True:
            time.sleep(10)

    except Exception as e:
        print("[-] Connection failed:", e)

if __name__ == "__main__":
    main()
