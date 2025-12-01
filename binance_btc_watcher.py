
import os
import requests
import time
from dotenv import load_dotenv

# Φόρτωση μεταβλητών από το .env
load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
WATCH_DIR = os.getenv("WATCH_DIR", "watch_incoming")
CHAIN_PATH = os.getenv("CHAIN_PATH", "phantom_tx_chain.json")

# Π.χ. κοινό address Binance cold wallet για παρακολούθηση εισερχομένων
TARGET_ADDRESS = "1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ"  # Binance

def check_btc_transactions(address):
    url = f"https://blockstream.info/api/address/{address}/txs"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[!] Error: {response.status_code}")
            return []
    except Exception as e:
        print(f"[!] Exception: {e}")
        return []

def process_transactions(txs):
    for tx in txs:
        outputs = tx.get("vout", [])
        for out in outputs:
            value_btc = out.get("value", 0) / 100000000  # satoshis → BTC
            if value_btc < 0.001:  # micro tx
                print(f"[+] Micro transaction detected: {value_btc} BTC")
                trigger_thronos_node(tx)

def trigger_thronos_node(tx):
    txid = tx.get("txid")
    print(f"🔥 Triggering Thronos node for TX: {txid}")
    # (εδώ μπορεί να γραφτεί σε αρχείο chain / ενεργοποίηση miner / σύνδεση με phantom_post_send.py)
    with open(CHAIN_PATH, "a") as f:
        f.write(f"# Auto-imported tx\n{txid}\n")

if __name__ == "__main__":
    print("[*] Monitoring Binance cold wallet for microtransactions...")
    while True:
        txs = check_btc_transactions(TARGET_ADDRESS)
        if txs:
            process_transactions(txs)
        time.sleep(60)  # κάθε λεπτό

