import requests, json, time

# -- Halving Logic --
def get_block_reward(height):
    base_reward = 1.0
    halving_interval = 210000
    epoch = height // halving_interval
    reward = base_reward / (2 ** epoch)
    return round(reward, 6)

# -- Send Block --
def send_block():
    block_height = int(time.time())  # substitute with real block height if needed
    reward = get_block_reward(block_height)
    pool_fee = 0.005
    reward_to_miner = round(reward - pool_fee, 6)

    block = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "miner_btc_address": "unknown",
        "referral": None,
        "reward": reward,
        "pool_fee": pool_fee,
        "reward_to_miner": reward_to_miner,
        "block_hash": f"THR-{block_height}"
    }

    try:
        res = requests.post("https://thrchain.up.railway.app/submit_block", json=block)
        print(f"Block sent (status {res.status_code}):")
        print(json.dumps(block, indent=2))
        print("Response:", res.text)
    except Exception as e:
        print("❌ Failed to send block:", e)

# -- Trigger --
if __name__ == "__main__":
    send_block()
