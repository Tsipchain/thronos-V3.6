import requests, time, json, hashlib
from datetime import datetime

PLEDGE_CHAIN = "pledge_chain.json"
CHAIN_FILE = "phantom_tx_chain.json"
SUBMIT_URL = "https://thrchain.up.railway.app/submit_block"
MINER_BTC = "3KUGVJ96T3JHuUrEHMeAvDKSo1zM9tD9nF"

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return []

def calculate_reward(height):
    halvings = height // 210000
    return round(1.0 / (2 ** halvings), 6)

def get_thr_address(btc_address):
    pledges = load_json(PLEDGE_CHAIN)
    p = next((p for p in pledges if p["btc_address"] == btc_address), None)
    return p["thr_address"] if p else None

def get_chain_height():
    chain = load_json(CHAIN_FILE)
    return len(chain)

def start_worker():
    thr_addr = get_thr_address(MINER_BTC)
    if not thr_addr:
        print("❌ No THR address found for pledge BTC:", MINER_BTC)
        return

    while True:
        height = get_chain_height()
        reward = calculate_reward(height)
        fee = 0.005
        to_miner = round(reward - fee, 6)

        block = {
            "thr_address": thr_addr,
            "miner_btc_address": MINER_BTC,
            "block_hash": f"THR-survival-{int(time.time())}",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "reward": reward,
            "pool_fee": fee,
            "reward_to_miner": to_miner
        }

        try:
            r = requests.post(SUBMIT_URL, json=block, timeout=15)
            print("⇨", r.status_code, r.json())
        except Exception as e:
            print("✖️", e)

        time.sleep(60)

if __name__ == "__main__":
    start_worker()


