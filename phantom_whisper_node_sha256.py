import os
import json
import time
import uuid
import hashlib
import requests
from PIL import Image

WATCH_DIR = "watch_incoming"
ENCODED_DIR = "encoded_images"
TX_LOG = "phantom_logs/phantom_activity.log"
LEDGER_FILE = "ledger.json"

os.makedirs(WATCH_DIR, exist_ok=True)
os.makedirs(ENCODED_DIR, exist_ok=True)
os.makedirs(os.path.dirname(TX_LOG), exist_ok=True)

def calculate_sha256(image_path):
    with open(image_path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def generate_tx_payload(image_name, sha256_hash):
    block = int(time.time())
    sender = f"WhisperNode#{uuid.uuid4().hex[:6]}"
    signature = f"0x{uuid.uuid4().hex[:64]}"
    return {
        "tx": f"0x{sha256_hash}",
        "network": "mainnet",
        "block": block,
        "sender": sender,
        "signature": signature,
        "reward": 1.0,
        "pool_fee": 0.005,
        "reward_to_miner": round(1.0 - 0.005, 6),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "block_hash": f"THR-{int(time.time())}"
    }

def encode_payload_in_image(image_path, payload, output_path):
    img = Image.open(image_path).convert("RGB")
    payload_json = json.dumps(payload)
    payload_bits = ''.join([format(ord(c), '08b') for c in payload_json]) + '00000000'
    pixels = list(img.getdata())
    new_pixels = []
    bit_index = 0
    for pixel in pixels:
        r, g, b = pixel
        if bit_index < len(payload_bits):
            r = (r & ~1) | int(payload_bits[bit_index])
            bit_index += 1
        if bit_index < len(payload_bits):
            g = (g & ~1) | int(payload_bits[bit_index])
            bit_index += 1
        if bit_index < len(payload_bits):
            b = (b & ~1) | int(payload_bits[bit_index])
            bit_index += 1
        new_pixels.append((r, g, b))
    img.putdata(new_pixels)
    img.save(output_path)
    return payload

def log_activity(image_name, payload):
    with open(TX_LOG, "a") as f:
        f.write(json.dumps({"image": image_name, "payload": payload}) + "\n")

def update_ledger(sender, amount):
    ledger = {}
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE, "r") as f:
            ledger = json.load(f)
    ledger[sender] = round(ledger.get(sender, 0) + amount, 6)
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=2)

def watch_and_encode():
    print("👁️ WhisperNode active with SHA256. Watching for incoming images...")
    seen = set()
    while True:
        for file in os.listdir(WATCH_DIR):
            if file.lower().endswith(('.png', '.jpg', '.jpeg')) and file not in seen:
                seen.add(file)
                input_path = os.path.join(WATCH_DIR, file)
                output_path = os.path.join(ENCODED_DIR, file)
                sha256_hash = calculate_sha256(input_path)
                payload = generate_tx_payload(file, sha256_hash)
                encode_payload_in_image(input_path, payload, output_path)
                log_activity(file, payload)
                update_ledger(payload["sender"], payload["reward_to_miner"])
                try:
                    res = requests.post("https://thrchain.up.railway.app/submit_block", json=payload)
                    if res.status_code == 200:
                        try:
                            response_data = res.json()
                            print(f"📡 Block submitted → {res.status_code}: {response_data}")
                        except ValueError:
                             print(f"📡 Block submitted → {res.status_code}: Server did not return valid JSON. Response text: {res.text}")
                    else:
                        print(f"📡 Block submitted → Server error: {res.status_code}. Response text: {res.text}")

                except Exception as e:
                    print(f"❌ Failed to submit block: {e}")
                print(f"✅ Embedded TX in {file} | THR Addr: {payload['sender']}")
        time.sleep(5)

if __name__ == "__main__":
    watch_and_encode()