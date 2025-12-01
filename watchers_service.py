import time
import json
import os
import requests

# Configuration
WATCH_ADDRESS = "1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ" # The Thronos BTC Receiver
LEDGER_FILE = "watcher_ledger.json"
EXCHANGE_RATE = 10000 # 1 BTC = 10000 THR (based on 1 THR = 0.0001 BTC)

def load_ledger():
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE, 'r') as f:
            return json.load(f)
    return []

def save_ledger(data):
    with open(LEDGER_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def check_btc_deposits(address):
    # Query blockchain.info API
    url = f"https://blockchain.info/rawaddr/{address}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('txs', [])
    except Exception as e:
        print(f"⚠️ API Error: {e}")
    return []

def mint_thr_on_thronos(btc_tx, amount_thr):
    # Placeholder for calling Thronos API
    print(f"🔨 Minting {amount_thr} THR for BTC TX {btc_tx['hash']}")
    # Example: requests.post("http://localhost:3333/admin/mint", json={...})

def notify_off_chain_agent(btc_tx):
    # Placeholder for IoT / ATM notification
    print(f"📡 Notifying Off-Chain Agents for TX {btc_tx['hash']}")

def run_watcher():
    print(f"👀 Watcher Service Started on {WATCH_ADDRESS}")
    processed_txs = set()
    
    # Load existing to avoid reprocessing
    ledger = load_ledger()
    for entry in ledger:
        processed_txs.add(entry['btc_tx_hash'])
        
    # Run one check cycle
    txs = check_btc_deposits(WATCH_ADDRESS)
    
    new_entries = []
    
    for tx in txs:
        tx_hash = tx['hash']
        if tx_hash in processed_txs:
            continue
            
        # Check outputs for our address
        amount_sats = 0
        for out in tx['out']:
            if out.get('addr') == WATCH_ADDRESS:
                amount_sats += out.get('value', 0)
                
        if amount_sats > 0:
            amount_btc = amount_sats / 100000000
            amount_thr = amount_btc * EXCHANGE_RATE
            
            entry = {
                "btc_tx_hash": tx_hash,
                "timestamp": tx['time'],
                "amount_btc": amount_btc,
                "amount_thr": amount_thr,
                "status": "detected"
            }
            
            print(f"💰 Deposit Detected: {amount_btc} BTC -> {amount_thr} THR")
            
            mint_thr_on_thronos(tx, amount_thr)
            notify_off_chain_agent(tx)
            
            ledger.append(entry)
            processed_txs.add(tx_hash)
            new_entries.append(entry)
            
    if new_entries:
        save_ledger(ledger)
        print(f"✅ Logged {len(new_entries)} new deposits.")
    else:
        print("💤 No new deposits found.")

if __name__ == "__main__":
    run_watcher()