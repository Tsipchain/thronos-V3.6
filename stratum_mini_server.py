# Mini Stratum-compatible server for Thronos Pool
import socket
import threading

def handle_client(conn, addr):
    print(f"[NEW CONNECTION] {addr} connected.")
    conn.send(b"Welcome to Thronos Stratum Pool\n")
    while True:
        try:
            data = conn.recv(1024)
            if not data:
                break
            print(f"[{addr}] {data.decode().strip()}")
            # εδώ μπορείς να στείλεις job, target κ.λπ.
            conn.send(b"OK\n")
        except ConnectionResetError:
            break
    conn.close()

def start_stratum_server(host='0.0.0.0', port=3334):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    print(f"[LISTENING] Stratum server running on {host}:{port}")
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()

if __name__ == "__main__":
    start_stratum_server()

