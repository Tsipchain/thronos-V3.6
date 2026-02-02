#!/usr/bin/env python3
# Thronos CPU PoW Miner (generic kit)
#
# 1. Set your THR address in THR_ADDRESS.
# 2. Run:  pip install requests
# 3. Run:  python pow_miner_cpu.py

import hashlib
import os
import time
import requests
import json
import sys

# Configuration
THR_ADDRESS = "THR_PUT_YOUR_ADDRESS_HERE"  # Replace with your actual THR address
SERVER_URL = os.getenv("THRONOS_SERVER_URL", os.getenv("THRONOS_SERVER", "https://thrchain.up.railway.app"))
SUBMIT_RETRIES = int(os.getenv("THRONOS_SUBMIT_RETRIES", "3"))
SUBMIT_RETRY_DELAY = float(os.getenv("THRONOS_SUBMIT_RETRY_DELAY", "2"))

def get_mining_work():
    """Fetches mining work (job_id, target, prev_hash, height)."""
    try:
        r = requests.get(
            f"{SERVER_URL}/api/miner/work",
            params={"address": THR_ADDRESS},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("ok") is False:
            print(f"⚠️ Mining work rejected: {data.get('error')}")
            return None
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error fetching work: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error fetching work: {e}")
        return None

def mine_block(work):
    """
    CPU mining with dynamic difficulty:
    - Fetches target from server
    - Tries nonces until hash < target
    """
    if not work:
        print("⚠️ Could not fetch mining work. Retrying...")
        return None

    target_hex = work.get("target", "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
    target = int(target_hex, 16)
    reward = work.get("reward", 0)
    job_id = work.get("job_id")
    expires_at = work.get("expires_at")
    
    print(f"⛏️  Starting mining for {THR_ADDRESS}")
    last_hash = work.get("prev_hash") or "0" * 64
    tip_height = work.get("height")
    print(f"   Last Hash: {last_hash[:16]}...")
    print(f"   Target:    {target_hex[:16]}...")
    if reward:
        print(f"   Reward:    {reward} THR")
    if job_id:
        print(f"   Job ID:    {job_id}")

    nonce = 0
    start = time.time()
    last_status_time = start
    
    while True:
        # Refresh info every 30 seconds or if block found elsewhere
        if expires_at and time.time() >= float(expires_at):
            print("🔄 Work expired. Restarting mining...")
            return None

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
                "job_id": job_id,
            }
            if tip_height is not None:
                block["height"] = int(tip_height)
            return block

        nonce += 1
        # time.sleep(0.0001) 

def submit_block(block):
    """Submits the mined block to the server."""
    attempts = max(1, SUBMIT_RETRIES)
    delay = max(0.5, SUBMIT_RETRY_DELAY)
    for attempt in range(1, attempts + 1):
        try:
            r = requests.post(f"{SERVER_URL}/api/miner/submit", json=block, timeout=10)
            if r.status_code == 200:
                print(f"📬 Submission successful: {r.json()}")
                return True
            if r.status_code == 409:
                print("🔄 Stale work detected. Refreshing work...")
                return False
            if r.status_code in {429, 500, 502, 503, 504}:
                print(f"⏳ Node busy (HTTP {r.status_code}). Retrying {attempt}/{attempts}...")
                if attempt < attempts:
                    time.sleep(delay)
                    delay *= 1.5
                    continue
            print(f"⚠️ Submission failed: {r.status_code} - {r.text}")
            return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Connection error submitting block: {e}")
            if attempt < attempts:
                time.sleep(delay)
                delay *= 1.5
                continue
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
        work = get_mining_work()
        if work:
            mined_block = mine_block(work)
            if mined_block:
                if not submit_block(mined_block):
                    time.sleep(1)
            
            time.sleep(2)
        else:
            print("⏳ Waiting for server connection...")
            time.sleep(5)
