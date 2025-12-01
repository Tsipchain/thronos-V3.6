import socket
import json

POOL = 'sha256.poolbinance.com'
PORT = 443

def connect_to_pool():
    try:
        sock = socket.create_connection((POOL, PORT))
        print(f"[+] Connected to {POOL}:{PORT}")
        # Here you'd implement TLS or stratum handshake if allowed
        # But most pools require secure protocol so this is a concept/mockup
    except Exception as e:
        print(f"[-] Could not connect to pool: {e}")

def main():
    print("=== Thronos Job Sniffer ===")
    connect_to_pool()

if __name__ == '__main__':
    main()