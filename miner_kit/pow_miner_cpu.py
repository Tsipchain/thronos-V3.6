#!/usr/bin/env python3
# Thronos CPU PoW Miner (generic kit)
#
# 1. Set your THR address in THR_ADDRESS.
# 2. Run:  pip install requests
# 3. Run:  python pow_miner_cpu.py

import hashlib
import time
import requests
import json
import sys

# Configuration
THR_ADDRESS = "THR_PUT_YOUR_ADDRESS_HERE"  # Replace with your actual THR address
SERVER_URL = "https://thrchain.up.railway.app" # Update if your server URL is different

def get_last_hash():
    """Fetches the last block hash from the Thronos server."""
    try:
        r = requests.get(f"{SERVER_URL}/last_block_hash", timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("last_hash", "0" * 64)
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error fetching last hash: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error fetching last hash: {e}")
        return None

def get_mining_info():
    """Fetches dynamic mining info (target, difficulty, reward)."""
    try:
        r = requests.get(f"{SERVER_URL}/mining_info", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"❌ Error fetching mining info: {e}")
        return None

def mine_block(last_hash):
    """
    CPU mining with dynamic difficulty:
    - Fetches target from server
    - Tries nonces until hash < target
    """
    info = get_mining_info()
    if not info:
        print("⚠️ Could not fetch mining info. Retrying...")
        return None

    target_hex = info.get("target", "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
    target = int(target_hex, 16)
    difficulty = info.get("difficulty_int", 1)
    reward = info.get("reward", 0)
    
    print(f"⛏️  Starting mining for {THR_ADDRESS}")
    print(f"   Last Hash: {last_hash[:16]}...")
    print(f"   Target:    {target_hex[:16]}... (Diff: ~{difficulty})")
    print(f"   Reward:    {reward} THR")

    nonce = 0
    start = time.time()
    last_status_time = start
    
    while True:
        # Refresh info every 30 seconds or if block found elsewhere
        if time.time() - start > 30:
             current_server_hash = get_last_hash()
             if current_server_hash and current_server_hash != last_hash:
                 print("🔄 New block found on network. Restarting mining...")
                 return None
             
             # Refresh target just in case
             new_info = get_mining_info()
             if new_info:
                 target = int(new_info.get("target", target_hex), 16)
                 
             start = time.time() 

        nonce_str = str(nonce).encode()
        data = (last_hash + THR_ADDRESS).encode() + nonce_str
        h_hex = hashlib.sha256(data).hexdigest()
        h_int = int(h_hex, 16)

        if time.time() - last_status_time > 10:
            elapsed = time.time() - start
            hashrate = nonce / elapsed if elapsed > 0 else 0
            print(f"[{THR_ADDRESS}] nonce={nonce} hash={h_hex[:16]}... ({hashrate:.1f} H/s)")
            last_status_time = time.time()

        if h_int <= target:
            duration = time.time() - start
            print(f"✅ Found valid nonce after {nonce} tries in {duration:.1f}s")
            print(f"   Hash: {h_hex}")
            block = {
                "thr_address": THR_ADDRESS,
                "nonce": nonce,
                "pow_hash": h_hex,
                "prev_hash": last_hash,
            }
            return block

        nonce += 1
        # time.sleep(0.0001) 

def submit_block(block):
    """Submits the mined block to the server."""
    try:
        r = requests.post(f"{SERVER_URL}/submit_block", json=block, timeout=10)
        if r.status_code == 200:
            print(f"📬 Submission successful: {r.json()}")
            return True
        else:
            print(f"⚠️ Submission failed: {r.status_code} - {r.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error submitting block: {e}")
        return False
    except Exception as e:
        print(f"❌ Error submitting block: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        THR_ADDRESS = sys.argv[1]
    
    if "THR_PUT_YOUR_ADDRESS_HERE" in THR_ADDRESS:
        print("⚠️  Please set your THR_ADDRESS in the script or pass it as an argument.")
        print("   Usage: python pow_miner_cpu.py <YOUR_THR_ADDRESS>")
        sys.exit(1)

    print(f"🚀 Thronos CPU Miner started for address: {THR_ADDRESS}")
    print(f"📡 Server: {SERVER_URL}")
    
    while True:
        last_hash = get_last_hash()
        if last_hash:
            mined_block = mine_block(last_hash)
            if mined_block:
                submit_block(mined_block)
            
            time.sleep(2)
        else:
            print("⏳ Waiting for server connection...")
            time.sleep(5)