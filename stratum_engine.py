"""
stratum_engine.py
~~~~~~~~~~~~~~~~~~

A very simple Stratum job server for ThronosChain.  This engine accepts
incoming TCP connections from SHA‑256 miners on port 3333 and exchanges
minimal Stratum protocol messages.  It is intended as a **placeholder** to
enable miners (such as cgminer, bfgminer or USB sticks) to connect during
development.  The server currently issues a fixed job template and does not
validate shares or record work.

In a production environment, the Stratum engine would need to assemble block
templates from the local blockchain state, assign unique extranonces and
difficulty targets to connected miners, validate incoming shares against the
current target and credit miners with rewards.  This demonstration server
provides only the handshake and a static job for illustrative purposes.
"""

import json
import os
import select
import socket
import threading
import time


HOST = os.getenv("STRATUM_HOST", "0.0.0.0")
PORT = int(os.getenv("STRATUM_PORT", "3333"))


def build_static_job() -> dict:
    """Build a static mining job for demonstration purposes.

    Returns
    -------
    dict
        A minimal Stratum job JSON object containing dummy values.  Miners
        connecting to this server will be assigned the same job.
    """
    job_id = int(time.time())
    # In a real implementation, `prev_hash` and `merkle_root` must reflect
    # the current block template.  Here we use placeholder values.
    return {
        "id": job_id,
        "prev_hash": "00" * 32,
        "merkle_root": "11" * 32,
        "version": 536870912,
        "bits": "1d00ffff",
        "time": int(time.time()),
        "clean_jobs": True,
    }


def handle_client(conn: socket.socket, addr: tuple) -> None:
    """Handle an individual miner connection.

    This function reads a subscription request, responds with a minimal
    `mining.subscribe` response and then sends a single `mining.notify`
    containing a static job.  The client connection is kept open until the
    remote end closes it or the server is shut down.
    """
    print(f"[Stratum] New connection from {addr}")
    try:
        # Read subscription message from client
        data = conn.recv(1024)
        if not data:
            return
        try:
            msg = data.decode().strip()
        except Exception:
            msg = str(data)
        print(f"[Stratum] Received: {msg}")
        # Respond with a basic subscription ack
        # Format: [message_id, [extranonce1, extranonce2], extranonce_size]
        sub_resp = [1, ["deadbeef", "cafebabe"], 4]
        conn.sendall(json.dumps(sub_resp).encode() + b"\n")
        # Send a single job notification
        job = build_static_job()
        notif = [
            "mining.notify",
            job["id"],
            job["prev_hash"],
            job["merkle_root"],
            format(job["time"], "x"),
            job["bits"],
            True,
        ]
        conn.sendall(json.dumps(notif).encode() + b"\n")
        # Keep the connection alive until client disconnects
        while True:
            ready, _, _ = select.select([conn], [], [], 30)
            if conn in ready:
                data = conn.recv(1024)
                if not data:
                    break
                # Here we would process share submissions
                # For now, just log the incoming data
                print(f"[Stratum] Share from {addr}: {data.strip()}\n")
    except Exception as exc:
        print(f"[Stratum] Error handling client {addr}: {exc}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        print(f"[Stratum] Connection closed {addr}")


def start_server() -> None:
    """Start the Stratum server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(5)
        print(f"[Stratum] Listening on {HOST}:{PORT}")
        try:
            while True:
                conn, addr = srv.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            print("[Stratum] Server shutting down")


if __name__ == "__main__":
    start_server()