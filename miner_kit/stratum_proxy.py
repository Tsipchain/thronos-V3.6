import socket
import threading
import json
import time
import requests
import struct
import binascii
import hashlib

# Configuration
THRONOS_SERVER = "http://localhost:3333"
STRATUM_PORT = 3334
POLL_INTERVAL = 1.0

# Global State
current_job = None
job_id_counter = 0
clients = []
lock = threading.Lock()

def sha256d(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def hex_to_bytes(h):
    return binascii.unhexlify(h)

def bytes_to_hex(b):
    return binascii.hexlify(b).decode()

def reverse_bytes(h):
    """Reverses hex string byte-wise (for LE/BE conversion)."""
    b = hex_to_bytes(h)
    return bytes_to_hex(b[::-1])

class Job:
    def __init__(self, job_id, prev_hash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs):
        self.job_id = job_id
        self.prev_hash = prev_hash
        self.coinb1 = coinb1
        self.coinb2 = coinb2
        self.merkle_branch = merkle_branch
        self.version = version
        self.nbits = nbits
        self.ntime = ntime
        self.clean_jobs = clean_jobs

def get_mining_info():
    try:
        r1 = requests.get(f"{THRONOS_SERVER}/last_block_hash", timeout=2)
        last_block = r1.json()
        
        r2 = requests.get(f"{THRONOS_SERVER}/mining_info", timeout=2)
        info = r2.json()
        
        return last_block, info
    except Exception as e:
        print(f"Error fetching mining info: {e}")
        return None, None

def job_updater():
    global current_job, job_id_counter
    
    last_prev_hash = None
    
    print(f"Stratum Proxy listening on 0.0.0.0:{STRATUM_PORT}")
    print(f"Connected to Thronos Server at {THRONOS_SERVER}")
    
    while True:
        last_block, info = get_mining_info()
        
        if last_block and info:
            prev_hash = last_block.get("last_hash", "0"*64)
            
            # Check if new block
            if prev_hash != last_prev_hash:
                with lock:
                    job_id_counter += 1
                    job_id = hex(job_id_counter)[2:]
                    
                    # Stratum expects prev_hash in Big Endian (swapped 32-bit words usually, but standard stratum is just LE reversed? 
                    # Actually, standard Stratum documentation says prevhash is BE.
                    # Thronos server returns prev_hash as hex string (likely BE from explorer view, but let's assume standard hex).
                    # We need to send it in the format the miner expects. 
                    # Usually miners expect it byte-swapped.
                    # Let's try sending it byte-reversed.
                    prev_hash_be = reverse_bytes(prev_hash)
                    
                    # Coinbase generation
                    # We create a dummy coinbase. The miner will append extranonce1 + extranonce2.
                    # Thronos doesn't validate the coinbase content strictly, just the merkle root.
                    # Coinb1: Version(4) + InputCount(1) + Input(Dummy)
                    coinb1 = "01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff0403" 
                    # Coinb2: Sequence(4) + OutputCount(1) + Output(Dummy) + LockTime(4)
                    coinb2 = "ffffffff0100f2052a010000001976a914123456789012345678901234567890123456789088ac00000000"
                    
                    merkle_branch = [] # No other txs
                    version = "00000001" # Version 1
                    
                    # nbits from server is hex string "0x..."
                    nbits_hex = info.get("nbits", "1d00ffff").replace("0x", "")
                    # Ensure 8 chars
                    nbits_hex = nbits_hex.zfill(8)
                    # Stratum usually wants it BE
                    nbits_be = reverse_bytes(nbits_hex)
                    
                    ntime = int(time.time())
                    ntime_hex = hex(ntime)[2:].zfill(8)
                    ntime_be = reverse_bytes(ntime_hex)
                    
                    clean_jobs = True
                    
                    current_job = Job(job_id, prev_hash_be, coinb1, coinb2, merkle_branch, version, nbits_be, ntime_be, clean_jobs)
                    last_prev_hash = prev_hash
                    
                    print(f"New Job #{job_id}: PrevHash={prev_hash[:8]}... nBits={nbits_hex}")
                    
                    notify_clients()
                    
        time.sleep(POLL_INTERVAL)

def notify_clients():
    if not current_job:
        return
        
    params = [
        current_job.job_id,
        current_job.prev_hash,
        current_job.coinb1,
        current_job.coinb2,
        current_job.merkle_branch,
        current_job.version,
        current_job.nbits,
        current_job.ntime,
        current_job.clean_jobs
    ]
    
    msg = json.dumps({
        "id": None,
        "method": "mining.notify",
        "params": params
    }) + "\n"
    
    for c in clients:
        try:
            c.sendall(msg.encode())
        except:
            pass

def handle_client(conn, addr):
    print(f"Client connected: {addr}")
    
    # Extranonce1 generation (unique per client)
    extranonce1 = hex(random.randint(0, 2**31))[2:].zfill(8)
    extranonce2_size = 4
    
    thr_address = "UNKNOWN"
    
    f = conn.makefile('r')
    
    try:
        for line in f:
            if not line: break
            try:
                req = json.loads(line)
            except:
                continue
                
            msg_id = req.get("id")
            method = req.get("method")
            params = req.get("params", [])
            
            response = None
            
            if method == "mining.subscribe":
                # Return [ [ ["mining.set_difficulty", "subscription_id_1"], ["mining.notify", "subscription_id_2"] ], extranonce1, extranonce2_size ]
                response = {
                    "id": msg_id,
                    "result": [
                        [["mining.set_difficulty", "1"], ["mining.notify", "1"]],
                        extranonce1,
                        extranonce2_size
                    ],
                    "error": None
                }
                
            elif method == "mining.authorize":
                thr_address = params[0]
                print(f"Miner Authorized: {thr_address}")
                response = {
                    "id": msg_id,
                    "result": True,
                    "error": None
                }
                # Send current job immediately
                if current_job:
                    notify_params = [
                        current_job.job_id,
                        current_job.prev_hash,
                        current_job.coinb1,
                        current_job.coinb2,
                        current_job.merkle_branch,
                        current_job.version,
                        current_job.nbits,
                        current_job.ntime,
                        current_job.clean_jobs
                    ]
                    notify_msg = json.dumps({
                        "id": None,
                        "method": "mining.notify",
                        "params": notify_params
                    }) + "\n"
                    conn.sendall(notify_msg.encode())
                    
            elif method == "mining.submit":
                # params: worker_name, job_id, extranonce2, ntime, nonce
                if len(params) >= 5:
                    job_id_sub = params[1]
                    extranonce2 = params[2]
                    ntime_hex = params[3]
                    nonce_hex = params[4]
                    
                    if current_job and job_id_sub == current_job.job_id:
                        # Reconstruct block to calculate Merkle Root
                        # Coinbase = coinb1 + extranonce1 + extranonce2 + coinb2
                        coinbase_hex = current_job.coinb1 + extranonce1 + extranonce2 + current_job.coinb2
                        coinbase_bin = hex_to_bytes(coinbase_hex)
                        
                        # Calculate Merkle Root (Double SHA256 of coinbase)
                        merkle_root_bin = sha256d(coinbase_bin)
                        merkle_root_hex = bytes_to_hex(merkle_root_bin)
                        
                        # Prepare submission for Thronos Server
                        # Server expects: thr_address, nonce (int), merkle_root (hex), prev_hash (hex), time (int), nbits (int), version
                        
                        # Convert nonce hex to int
                        nonce_int = int(nonce_hex, 16)
                        
                        # Convert ntime hex to int
                        ntime_int = int(ntime_hex, 16)
                        
                        # nbits is stored in current_job as BE hex string. 
                        # Server expects integer representation of the compact bits? 
                        # Or just the bits value. Let's send the integer value of the bits field.
                        # current_job.nbits is BE hex (e.g. "1d00ffff" -> reversed "ffff001d")
                        # Wait, reverse_bytes("1d00ffff") -> "ffff001d".
                        # We need to send the original "1d00ffff" integer value to server?
                        # Server: `header += struct.pack("<I", nbits)`
                        # So server expects the integer that, when packed LE, matches the header bits.
                        # The header bits are usually "1d00ffff" (0x1d00ffff).
                        # 0x1d00ffff packed LE is ff ff 00 1d.
                        # So we should send int(0x1d00ffff).
                        # current_job.nbits is "ffff001d" (BE of "1d00ffff").
                        # So we reverse it back to get "1d00ffff".
                        nbits_orig_hex = reverse_bytes(current_job.nbits)
                        nbits_int = int(nbits_orig_hex, 16)
                        
                        # Prev Hash: Server expects hex string.
                        # current_job.prev_hash is BE (reversed). We need to reverse it back to LE/Server format.
                        prev_hash_server = reverse_bytes(current_job.prev_hash)
                        
                        payload = {
                            "thr_address": thr_address,
                            "nonce": nonce_int,
                            "merkle_root": merkle_root_hex,
                            "prev_hash": prev_hash_server,
                            "time": ntime_int,
                            "nbits": nbits_int,
                            "version": 1,
                            "pow_hash": "00" # Placeholder, server calculates it
                        }
                        
                        print(f"Submitting share: Nonce={nonce_int} Merkle={merkle_root_hex[:8]}")
                        
                        try:
                            r = requests.post(f"{THRONOS_SERVER}/submit_block", json=payload, timeout=5)
                            res_json = r.json()
                            
                            if r.status_code == 200:
                                print("✅ Share Accepted!")
                                response = {"id": msg_id, "result": True, "error": None}
                            else:
                                print(f"❌ Share Rejected: {res_json.get('error')}")
                                response = {"id": msg_id, "result": False, "error": [20, res_json.get('error'), None]}
                        except Exception as e:
                            print(f"Submission Error: {e}")
                            response = {"id": msg_id, "result": False, "error": [21, "Server Error", None]}
                    else:
                        response = {"id": msg_id, "result": False, "error": [21, "Stale Job", None]}
            
            if response:
                conn.sendall((json.dumps(response) + "\n").encode())
                
    except Exception as e:
        print(f"Client Error: {e}")
    finally:
        conn.close()
        if conn in clients:
            clients.remove(conn)

import random

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", STRATUM_PORT))
    server.listen(5)
    
    # Start Job Updater
    t = threading.Thread(target=job_updater)
    t.daemon = True
    t.start()
    
    while True:
        conn, addr = server.accept()
        clients.append(conn)
        t_client = threading.Thread(target=handle_client, args=(conn, addr))
        t_client.daemon = True
        t_client.start()

if __name__ == "__main__":
    start_server()