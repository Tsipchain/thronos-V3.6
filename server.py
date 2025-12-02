# server.py
# ThronosChain server:
# - pledge + secure PDF (AES + QR + stego)
# - wallet + mining rewards
# - data volume (/app/data)
# - whitelist για free pledges
# - ασφαλές THR send με auth_secret (seed) ανά THR address
# - migration για ήδη υπάρχοντα pledges -> send_seed / send_auth_hash
# - last_block.json για σταθερό viewer/home status
# - recovery flow via steganography
# - Dynamic Difficulty & Halving
# - AI Agent Auto-Registration
# - Token Chart & Network Stats
# - Bitcoin Bridge Watcher & IoT Nodes
# - SHA256d PoW Support
# - Quantum-Secured AI Chat
# - AI Autonomous Driving Service
# - Mempool & 80/10/10 Reward Split (V3.6)

import os
import json
import time
import hashlib
import logging
import secrets
import random
import uuid
import zipfile
import io
import struct
import binascii
from datetime import datetime
from PIL import Image

import requests
from flask import (
    Flask, request, jsonify,
    render_template, send_from_directory,
    redirect, url_for, send_file
)
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler

from phantom_gateway_mainnet import get_btc_txns
from secure_pledge_embed import create_secure_pdf_contract
from phantom_decode import decode_payload_from_image
from ai_agent_service import ThronosAI

# ─── CONFIG ────────────────────────────────────────
app = Flask(__name__)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

DATA_DIR   = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

LEDGER_FILE   = os.path.join(DATA_DIR, "ledger.json")
CHAIN_FILE    = os.path.join(DATA_DIR, "phantom_tx_chain.json")
PLEDGE_CHAIN  = os.path.join(DATA_DIR, "pledge_chain.json")
LAST_BLOCK_FILE = os.path.join(DATA_DIR, "last_block.json")
WHITELIST_FILE = os.path.join(DATA_DIR, "free_pledge_whitelist.json")
AI_CREDS_FILE = os.path.join(DATA_DIR, "ai_agent_credentials.json")
WATCHER_LEDGER_FILE = os.path.join(DATA_DIR, "watcher_ledger.json")
IOT_DATA_FILE = os.path.join(DATA_DIR, "iot_data.json")
MEMPOOL_FILE = os.path.join(DATA_DIR, "mempool.json")

ADMIN_SECRET   = os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW")

BTC_RECEIVER  = "1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ"
MIN_AMOUNT    = 0.00001

CONTRACTS_DIR = os.path.join(DATA_DIR, "contracts")
os.makedirs(CONTRACTS_DIR, exist_ok=True)

UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

SEND_FEE = 0.0015

# --- Mining Config ---
# Initial difficulty: 5 hex zeros (20 bits). 2^256 / 2^20 = 2^236
INITIAL_TARGET = 2 ** 236
TARGET_BLOCK_TIME = 60  # seconds
RETARGET_INTERVAL = 10  # blocks

AI_WALLET_ADDRESS = "THR_AI_AGENT_WALLET_V1"
BURN_ADDRESS = "0x0"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pledge")

# Initialize AI
ai_agent = ThronosAI()

# ─── HELPERS ───────────────────────────────────────
def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_mempool():
    return load_json(MEMPOOL_FILE, [])

def save_mempool(pool):
    save_json(MEMPOOL_FILE, pool)

def sha256d(data):
    """Double SHA-256 hash."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def target_to_bits(target):
    """Converts a target integer to compact 'nbits' format."""
    if target == 0:
        return 0
    target_hex = hex(target)[2:]
    if len(target_hex) % 2 != 0:
        target_hex = "0" + target_hex

    # Convert to bytes
    target_bytes = bytes.fromhex(target_hex)

    # If the first bit is 1 (>= 0x80), we need to prepend a zero byte
    # because compact format is signed but target is unsigned
    if target_bytes[0] >= 0x80:
        target_bytes = b"\x00" + target_bytes

    exponent = len(target_bytes)
    coefficient = target_bytes[:3]

    # If we have fewer than 3 bytes, pad right with zeros
    if len(coefficient) < 3:
        coefficient = coefficient + b"\x00" * (3 - len(coefficient))

    # Combine: exponent (1 byte) + coefficient (3 bytes)
    # But exponent is stored as the most significant byte
    bits_val = (exponent << 24) | int.from_bytes(coefficient, "big")
    return bits_val


def calculate_reward(height: int) -> float:
    """
    Halving Schedule:
    Epoch 0 (0-209,999): 1.0 THR
    Halves every 210,000 blocks.
    Ends after Epoch 9 (2,100,000+ blocks).
    """
    halvings = height // 210000
    if halvings > 9:
        return 0.0
    return round(1.0 / (2 ** halvings), 6)


def update_last_block(entry, is_block=True):
    summary = {
        "height": entry.get("height"),
        "block_hash": entry.get("block_hash") or entry.get("tx_id"),
        "timestamp": entry.get("timestamp"),
        "thr_address": entry.get("thr_address"),
        "type": "block" if is_block else entry.get("type", "transfer"),
    }
    save_json(LAST_BLOCK_FILE, summary)


def verify_btc_payment(btc_address, min_amount=MIN_AMOUNT):
    try:
        txns = get_btc_txns(btc_address, BTC_RECEIVER)
        paid = any(
            tx["to"] == BTC_RECEIVER and tx["amount_btc"] >= min_amount
            for tx in txns
        )
        return paid, txns
    except Exception as e:
        logger.error(f"Watcher Error: {e}")
        return False, []


def get_mining_target():
    """
    Calculates the required target for the NEXT block based on DDA.
    """
    chain = load_json(CHAIN_FILE, [])
    # Filter only blocks (not transfers)
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]

    if len(blocks) < RETARGET_INTERVAL:
        return INITIAL_TARGET

    last_block = blocks[-1]
    # Default to INITIAL_TARGET if 'target' key missing (e.g. old blocks or pledge blocks)
    last_target = int(last_block.get("target", INITIAL_TARGET))

    # Only adjust if we hit the interval
    if len(blocks) % RETARGET_INTERVAL != 0:
        return last_target

    # Retarget Logic
    start_block = blocks[-RETARGET_INTERVAL]

    try:
        t_fmt = "%Y-%m-%d %H:%M:%S UTC"
        t_end = datetime.strptime(last_block["timestamp"], t_fmt).timestamp()
        t_start = datetime.strptime(start_block["timestamp"], t_fmt).timestamp()
    except Exception as e:
        logger.error(f"Time parse error during retarget: {e}")
        return last_target

    actual_time = t_end - t_start
    expected_time = RETARGET_INTERVAL * TARGET_BLOCK_TIME

    if actual_time <= 0:
        actual_time = 1

    ratio = actual_time / expected_time
    # Clamp oscillation
    if ratio < 0.25:
        ratio = 0.25
    if ratio > 4.00:
        ratio = 4.00

    new_target = int(last_target * ratio)

    # Clamp to min difficulty (max target)
    if new_target > INITIAL_TARGET:
        new_target = INITIAL_TARGET

    return new_target


# ─── VIEWER HELPER ─────────────────────────────────
def get_blocks_for_viewer():
    """
    Unified block list for thronos_block_viewer.html
    Shows: index, hash, fee_burned, reward_to_miner, reward_to_ai, is_stratum, nonce, transactions[]
    """
    chain = load_json(CHAIN_FILE, [])

    # Only entries that are blocks (have 'reward')
    raw_blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]

    blocks = []
    for b in raw_blocks:
        height = b.get("height")
        if height is None:
            height = len(blocks)

        block_hash = b.get("block_hash", "")
        nonce = b.get("nonce", "-")
        is_stratum = bool(b.get("is_stratum"))

        # Reward split
        rsplit = b.get("reward_split") or {}
        reward_to_miner = float(rsplit.get("miner", b.get("reward_to_miner", 0.0)))
        reward_to_ai    = float(rsplit.get("ai", 0.0))
        burn_from_split = float(rsplit.get("burn", 0.0))

        # Sum fees from TXs in the same height
        block_txs = [
            tx for tx in chain
            if tx.get("type") in ("transfer", "coinbase", "service_payment")
            and tx.get("height") == height
        ]
        fees_from_txs = sum(float(tx.get("fee_burned", 0.0)) for tx in block_txs)

        fee_burned = round(burn_from_split + fees_from_txs, 6)

        blocks.append({
            "index": height,
            "hash": block_hash,
            "fee_burned": fee_burned,
            "reward_to_miner": reward_to_miner,
            "reward_to_ai": reward_to_ai,
            "is_stratum": is_stratum,
            "nonce": nonce,
            "transactions": block_txs,
            "timestamp": b.get("timestamp", "")
        })

    blocks.sort(key=lambda x: x["index"], reverse=True)
    return blocks

def get_transactions_for_viewer():
    """
    Returns unified transaction list for thronos_block_viewer.html
    """
    chain = load_json(CHAIN_FILE, [])
    
    # Filter for transactions (type='transfer' or 'service_payment')
    txs = [
        t for t in chain 
        if isinstance(t, dict) and t.get("type") in ["transfer", "service_payment"]
    ]
    
    formatted_txs = []
    for t in txs:
        formatted_txs.append({
            "tx_id": t.get("tx_id", "Unknown"),
            "from": t.get("from", "Unknown"),
            "to": t.get("to", "Unknown"),
            "amount": t.get("amount", 0.0),
            "timestamp": t.get("timestamp", ""),
            "type": t.get("type", "transfer")
        })
        
    # Sort newest first
    formatted_txs.sort(key=lambda x: x["timestamp"], reverse=True)
    return formatted_txs

def ensure_ai_wallet():
    """
    Checks if the AI Wallet exists in the pledge chain.
    If not, creates a 'System Pledge' for it so it has a valid Send Secret.
    """
    pledges = load_json(PLEDGE_CHAIN, [])
    ai_pledge = next((p for p in pledges if p.get("thr_address") == AI_WALLET_ADDRESS), None)

    if not ai_pledge:
        print(f"🤖 Initializing AI Agent Wallet: {AI_WALLET_ADDRESS}")

        # Generate credentials
        send_seed = secrets.token_hex(16)
        send_seed_hash = hashlib.sha256(send_seed.encode()).hexdigest()
        send_auth_hash = hashlib.sha256(f"{send_seed}:auth".encode()).hexdigest()

        new_pledge = {
            "btc_address": "SYSTEM_AI_RESERVE",
            "pledge_text": "Thronos AI Agent Genesis Allocation",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "pledge_hash": "AI_GENESIS_" + secrets.token_hex(8),
            "thr_address": AI_WALLET_ADDRESS,
            "send_seed_hash": send_seed_hash,
            "send_auth_hash": send_auth_hash,
            "has_passphrase": False,
            "is_system": True,
        }

        pledges.append(new_pledge)
        save_json(PLEDGE_CHAIN, pledges)

        # Save credentials for the user/agent to use
        creds = {
            "thr_address": AI_WALLET_ADDRESS,
            "auth_secret": send_seed,
            "note": "Copy these into your ai_agent/agent_config.json",
        }
        save_json(AI_CREDS_FILE, creds)
        print(f"✅ AI Wallet Registered. Credentials saved to {AI_CREDS_FILE}")
    else:
        print(f"🤖 AI Wallet {AI_WALLET_ADDRESS} is already registered.")


def decode_iot_steganography(image_path):
    """
    Decodes LSB steganography from IoT node images.
    Format: JSON string + "###END###"
    """
    try:
        img = Image.open(image_path)
        width, height = img.size
        pixels = img.load()

        delimiter = "###END###"

        # Simplified extraction for MVP
        chars = []
        current_byte = ""

        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                for val in (r, g, b):
                    current_byte += str(val & 1)
                    if len(current_byte) == 8:
                        char = chr(int(current_byte, 2))
                        chars.append(char)
                        current_byte = ""

                        if len(chars) >= len(delimiter):
                            tail = "".join(chars[-len(delimiter):])
                            if tail == delimiter:
                                json_str = "".join(chars[:-len(delimiter)])
                                return json.loads(json_str)
        return None
    except Exception as e:
        print(f"Stego Decode Error: {e}")
        return None


# ─── BASIC PAGES ───────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/contracts/<path:filename>")
def serve_contract(filename):
    return send_from_directory(CONTRACTS_DIR, filename)


@app.route("/viewer")
def viewer():
    blocks = get_blocks_for_viewer()
    transactions = get_transactions_for_viewer()
    return render_template("thronos_block_viewer.html", blocks=blocks, transactions=transactions)


@app.route("/wallet")
def wallet_page():
    return render_template("wallet_viewer.html")


@app.route("/send")
def send_page():
    return render_template("send.html")


@app.route("/tokenomics")
def tokenomics_page():
    return render_template("tokenomics.html")


@app.route("/whitepaper")
def whitepaper_page():
    return render_template("whitepaper.html")


@app.route("/roadmap")
def roadmap_page():
    return render_template("roadmap.html")


@app.route("/token_chart")
def token_chart_page():
    return render_template("token_chart.html")


# ─── NEW SERVICES PAGES ────────────────────────────
@app.route("/bridge")
def bridge_page():
    return render_template("bridge.html")


@app.route("/iot")
def iot_page():
    return render_template("iot.html")


@app.route("/chat")
def chat_page():
    return render_template("chat.html")


# ─── RECOVERY FLOW ─────────────────────────────────
@app.route("/recovery")
def recovery_page():
    return render_template("recovery.html")


@app.route("/recover_submit", methods=["POST"])
def recover_submit():
    if "file" not in request.files:
        return jsonify(error="No file part"), 400
    file = request.files["file"]
    passphrase = request.form.get("passphrase", "").strip()

    if file.filename == "":
        return jsonify(error="No selected file"), 400

    if not passphrase:
        return jsonify(error="Passphrase is required"), 400

    if file:
        filename = secure_filename(file.filename)
        temp_path = os.path.join(DATA_DIR, f"temp_{int(time.time())}_{filename}")
        try:
            file.save(temp_path)
            payload = decode_payload_from_image(temp_path, passphrase)
            if os.path.exists(temp_path):
                os.remove(temp_path)

            if payload:
                return jsonify(status="success", payload=payload), 200
            else:
                return jsonify(error="Failed to decode or decrypt."), 400
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify(error=f"Server error: {str(e)}"), 500

    return jsonify(error="Unknown error"), 500


# ─── STATUS APIs ───────────────────────────────────
@app.route("/chain")
def get_chain():
    return jsonify(load_json(CHAIN_FILE, [])), 200


@app.route("/last_block")
def api_last_block():
    summary = load_json(LAST_BLOCK_FILE, {})
    return jsonify(summary), 200


@app.route("/last_block_hash")
def last_block_hash():
    chain = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    if blocks:
        last = blocks[-1]
        return jsonify(
            last_hash=last.get("block_hash", ""),
            height=len(blocks) - 1,
            timestamp=last.get("timestamp"),
        )
    else:
        return jsonify(last_hash="0" * 64, height=-1, timestamp=None)


@app.route("/mining_info")
def mining_info():
    target = get_mining_target()
    nbits = target_to_bits(target)

    chain = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    last_hash = blocks[-1].get("block_hash", "") if blocks else "0"*64

    height = len(chain)  # next height index in file
    reward = calculate_reward(height)
    mempool_len = len(load_mempool())

    return jsonify({
        "target": hex(target),
        "nbits": hex(nbits),
        "difficulty_int": int(INITIAL_TARGET // target),
        "reward": reward,
        "height": height,
        "last_hash": last_hash,
        "mempool": mempool_len
    }), 200


@app.route("/api/network_stats")
def network_stats():
    pledges = load_json(PLEDGE_CHAIN, [])
    chain = load_json(CHAIN_FILE, [])
    ledger = load_json(LEDGER_FILE, {})

    # Calculate some stats
    pledge_count = len(pledges)
    tx_count = len(chain)
    burned = ledger.get(BURN_ADDRESS, 0)
    ai_balance = ledger.get(AI_WALLET_ADDRESS, 0)

    # Get pledge growth over time
    pledge_dates = {}
    for p in pledges:
        # timestamp format: "2025-12-01 12:00:00 UTC"
        ts = p.get("timestamp", "").split(" ")[0]  # Just date
        pledge_dates[ts] = pledge_dates.get(ts, 0) + 1

    sorted_dates = sorted(pledge_dates.keys())
    cumulative_pledges = []
    running_total = 0
    for d in sorted_dates:
        running_total += pledge_dates[d]
        cumulative_pledges.append({"date": d, "count": running_total})

    return jsonify(
        {
            "pledge_count": pledge_count,
            "tx_count": tx_count,
            "burned": burned,
            "ai_balance": ai_balance,
            "pledge_growth": cumulative_pledges,
        }
    )

@app.route("/api/network_live")
def network_live():
    """
    Return rolling network stats: difficulty, est. hashrate, tx_count, mempool_len, avg_block_time
    """
    chain = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    mempool_len = len(load_mempool())

    # rolling window
    window = 20
    if len(blocks) < 2:
        avg_time = None
    else:
        tail = blocks[-min(window, len(blocks)):]
        try:
            t_fmt = "%Y-%m-%d %H:%M:%S UTC"
            t0 = datetime.strptime(tail[0]["timestamp"], t_fmt).timestamp()
            t1 = datetime.strptime(tail[-1]["timestamp"], t_fmt).timestamp()
            avg_time = (t1 - t0) / max(1, (len(tail) - 1))
        except Exception:
            avg_time = None

    target = get_mining_target()
    difficulty = int(INITIAL_TARGET // target)

    # Relative Bitcoin-style estimation
    hashrate = None
    if avg_time and avg_time > 0:
        hashrate = int(difficulty * (2**32) / avg_time)

    return jsonify({
        "difficulty": difficulty,
        "avg_block_time_sec": avg_time,
        "est_hashrate_hs": hashrate,   # hashes/second
        "tx_count": len(chain),
        "mempool": mempool_len
    }), 200


@app.route("/api/blocks")
def api_blocks():
    """JSON blocks for JS viewer etc."""
    blocks = get_blocks_for_viewer()
    return jsonify(blocks), 200


# ─── NEW SERVICES APIs ─────────────────────────────
@app.route("/api/bridge/data")
def bridge_data():
    """Returns the content of the watcher ledger."""
    data = load_json(WATCHER_LEDGER_FILE, [])
    return jsonify(data), 200


@app.route("/api/iot/data")
def iot_data():
    """Returns IoT vehicle data from the JSON store."""
    data = load_json(IOT_DATA_FILE, [])
    if not data:
        return jsonify([]), 200
    return jsonify(data), 200


@app.route("/api/iot/submit", methods=["POST"])
def iot_submit():
    """
    Receives a steganographically encoded image from a vehicle node.
    Decodes it and updates the IoT data store.
    """
    if "file" not in request.files:
        return jsonify(error="No file uploaded"), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify(error="No file selected"), 400

    try:
        # Save temp file
        filename = secure_filename(file.filename)
        temp_path = os.path.join(UPLOADS_DIR, f"iot_temp_{int(time.time())}_{filename}")
        file.save(temp_path)

        # Decode
        data = decode_iot_steganography(temp_path)

        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)

        if not data:
            return jsonify(error="Failed to decode steganography"), 400

        # Validate Data Structure
        if "vehicle_id" not in data:
            return jsonify(error="Invalid data format"), 400

        # Update IoT Data Store
        iot_list = load_json(IOT_DATA_FILE, [])

        # Remove old entry for this vehicle if exists
        iot_list = [v for v in iot_list if v.get("vehicle_id") != data["vehicle_id"]]

        # Add new entry
        iot_list.append(data)

        # Keep list size manageable
        if len(iot_list) > 100:
            iot_list = iot_list[-100:]

        save_json(IOT_DATA_FILE, iot_list)

        print(f"🚗 IoT Update: {data['vehicle_id']} | Odo: {data.get('odometer')}")
        return jsonify(status="success", vehicle_id=data["vehicle_id"]), 200

    except Exception as e:
        print(f"IoT Submit Error: {e}")
        return jsonify(error=str(e)), 500


@app.route("/api/iot/autonomous_request", methods=["POST"])
def iot_autonomous_request():
    """
    Handles requests from IoT nodes to activate AI Autonomous Driving.
    Requires THR payment.
    """
    data = request.get_json() or {}
    wallet = data.get("wallet")
    amount = data.get("amount", 0)
    
    if not wallet or amount <= 0:
        return jsonify(status="denied", message="Invalid request"), 400
        
    # Check Balance
    ledger = load_json(LEDGER_FILE, {})
    balance = float(ledger.get(wallet, 0.0))
    
    if balance < amount:
        return jsonify(status="denied", message="Insufficient THR funds"), 400
        
    # Process Payment (Send to AI Wallet)
    ledger[wallet] = round(balance - amount, 6)
    ledger[AI_WALLET_ADDRESS] = round(ledger.get(AI_WALLET_ADDRESS, 0.0) + amount, 6)
    save_json(LEDGER_FILE, ledger)
    
    # Log Transaction
    chain = load_json(CHAIN_FILE, [])
    tx = {
        "type": "service_payment",
        "service": "AI_AUTOPILOT",
        "from": wallet,
        "to": AI_WALLET_ADDRESS,
        "amount": amount,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": f"SRV-{len(chain)}-{int(time.time())}"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    
    print(f"🤖 AI Autopilot Activated for {wallet}. Payment: {amount} THR")
    
    return jsonify(status="granted", message="AI Driver Activated"), 200


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Handles chat requests to the AI Agent.
    """
    data = request.get_json() or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify(error="Message required"), 400

    result = ai_agent.generate_response(user_message)
    return jsonify(result), 200


@app.route("/register_node", methods=["POST"])
def register_node():
    """
    Registers a new IoT node and returns a downloadable zip kit.
    """
    address = request.form.get("address", "").strip()
    secret = request.form.get("secret", "").strip()

    if not address or not secret:
        return "Address and Secret are required", 400

    node_id = str(uuid.uuid4())

    # 1. Create node_config.json
    config = {
        "node_id": node_id,
        "wallet_address": address,
        "secret": secret,
        "server_url": "https://thrchain.up.railway.app",
    }
    config_json = json.dumps(config, indent=4)

    # 2. Create start_iot.py
    start_script = f"""
import os
import sys
import subprocess

print("Starting Thronos IoT Vehicle Node...")
print("Node ID: {node_id}")
print("Wallet: {address}")

# Auto-install dependencies
try:
    import PIL
    import requests
    import cryptography
except ImportError:
    print("Installing dependencies (pillow, requests, cryptography)...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "pillow", "cryptography"])

try:
    # Run the main node script
    subprocess.run([sys.executable, "iot_vehicle_node.py"], check=True)
except KeyboardInterrupt:
    print("\\nNode stopped.")
except Exception as e:
    print(f"Error: {{e}}")
    input("Press Enter to exit...")
"""

    # 3. Read iot_vehicle_node.py
    try:
        with open(os.path.join(BASE_DIR, "iot_vehicle_node.py"), "r") as f:
            node_script = f.read()
    except FileNotFoundError:
        node_script = "# iot_vehicle_node.py not found on server."

    # 4. Create Zip
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("node_config.json", config_json)
        zf.writestr("start_iot.py", start_script)
        zf.writestr("iot_vehicle_node.py", node_script)

        # Include PIC OF THE FIRE
        pic_path = os.path.join(BASE_DIR, "pic_of_the_fire.png")
        if os.path.exists(pic_path):
            zf.write(pic_path, "pic_of_the_fire.png")
        else:
            zf.writestr("pic_of_the_fire.png", "")

        zf.writestr(
            "README.txt",
            "1. Install Python 3.\n2. Run 'python start_iot.py' (it will auto-install dependencies).",
        )

    memory_file.seek(0)

    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"iot_node_kit_{node_id[:8]}.zip",
    )


# ─── PLEDGE FLOW ───────────────────────────────────
@app.route("/pledge")
def pledge_form():
    return render_template("pledge_form.html")


@app.route("/pledge_submit", methods=["POST"])
def pledge_submit():
    data = request.get_json() or {}
    btc_address = (data.get("btc_address") or "").strip()
    pledge_text = (data.get("pledge_text") or "").strip()
    passphrase = (data.get("passphrase") or "").strip()

    if not btc_address:
        return jsonify(error="Missing BTC address"), 400

    pledges = load_json(PLEDGE_CHAIN, [])
    exists = next((p for p in pledges if p["btc_address"] == btc_address), None)
    if exists:
        return jsonify(
            status="already_verified",
            thr_address=exists["thr_address"],
            pledge_hash=exists["pledge_hash"],
            pdf_filename=exists.get("pdf_filename", f"pledge_{exists['thr_address']}.pdf"),
        ), 200

    free_list = load_json(WHITELIST_FILE, [])
    is_dev_free = btc_address in free_list

    if is_dev_free:
        paid = True
        txns = []
    else:
        paid, txns = verify_btc_payment(btc_address)

    if not paid:
        return jsonify(
            status="pending",
            message="Waiting for BTC payment",
            txns=txns,
        ), 200

    thr_addr = f"THR{int(time.time() * 1000)}"
    phash = hashlib.sha256((btc_address + pledge_text).encode()).hexdigest()

    send_seed = secrets.token_hex(16)
    send_seed_hash = hashlib.sha256(send_seed.encode()).hexdigest()

    if passphrase:
        auth_string = f"{send_seed}:{passphrase}:auth"
    else:
        auth_string = f"{send_seed}:auth"

    send_auth_hash = hashlib.sha256(auth_string.encode()).hexdigest()

    pledge_entry = {
        "btc_address": btc_address,
        "pledge_text": pledge_text,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "pledge_hash": phash,
        "thr_address": thr_addr,
        "send_seed_hash": send_seed_hash,
        "send_auth_hash": send_auth_hash,
        "has_passphrase": bool(passphrase),
    }

    chain = load_json(CHAIN_FILE, [])
    height = len(chain)

    pdf_name = create_secure_pdf_contract(
        btc_address=btc_address,
        pledge_text=pledge_text,
        thr_address=thr_addr,
        pledge_hash=phash,
        height=height,
        send_seed=send_seed,
        output_dir=CONTRACTS_DIR,
        passphrase=passphrase,
    )

    pledge_entry["pdf_filename"] = pdf_name
    pledges.append(pledge_entry)
    save_json(PLEDGE_CHAIN, pledges)

    return jsonify(
        status="verified",
        thr_address=thr_addr,
        pledge_hash=phash,
        pdf_filename=pdf_name,
        send_secret=send_seed,
    ), 200


@app.route("/wallet_data/<thr_addr>")
def wallet_data(thr_addr):
    ledger = load_json(LEDGER_FILE, {})
    chain = load_json(CHAIN_FILE, [])
    bal = round(float(ledger.get(thr_addr, 0.0)), 6)

    history = [
        tx
        for tx in chain
        if isinstance(tx, dict)
        and (tx.get("from") == thr_addr or tx.get("to") == thr_addr)
    ]
    return jsonify(balance=bal, transactions=history), 200


@app.route("/wallet/<thr_addr>")
def wallet_redirect(thr_addr):
    return redirect(url_for("wallet_data", thr_addr=thr_addr)), 302


@app.route("/send_thr", methods=["POST"])
def send_thr():
    data = request.get_json() or {}

    from_thr    = (data.get("from_thr") or "").strip()
    to_thr      = (data.get("to_thr") or "").strip()
    amount_raw  = data.get("amount", 0)
    auth_secret = (data.get("auth_secret") or "").strip()
    passphrase  = (data.get("passphrase") or "").strip()

    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return jsonify(error="invalid_amount"), 400

    if not from_thr or not to_thr:
        return jsonify(error="missing_from_or_to"), 400
    if amount <= 0:
        return jsonify(error="amount_must_be_positive"), 400
    if not auth_secret:
        return jsonify(error="missing_auth_secret"), 400

    # Auth (same as before)
    pledges = load_json(PLEDGE_CHAIN, [])
    sender_pledge = next((p for p in pledges if p.get("thr_address") == from_thr), None)
    if not sender_pledge:
        return jsonify(error="unknown_sender_thr"), 404

    stored_auth_hash = sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(error="send_not_enabled_for_this_thr"), 400

    if sender_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(error="passphrase_required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    auth_hash = hashlib.sha256(auth_string.encode()).hexdigest()
    if auth_hash != stored_auth_hash:
        return jsonify(error="invalid_auth"), 403

    # Balance check (lock funds) — charge sender immediately,
    # fee is burned when TX is included in block.
    ledger = load_json(LEDGER_FILE, {})
    sender_balance = float(ledger.get(from_thr, 0.0))
    total_cost = amount + SEND_FEE
    if sender_balance < total_cost:
        return jsonify(error="insufficient_balance", balance=round(sender_balance, 6)), 400

    # Lock: deduct from sender, NOT yet credited to receiver (only when in block)
    ledger[from_thr] = round(sender_balance - total_cost, 6)
    save_json(LEDGER_FILE, ledger)

    # Put TX in mempool (no height yet)
    chain = load_json(CHAIN_FILE, [])
    tx = {
        "type": "transfer",
        "height": None,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "from": from_thr,
        "to": to_thr,
        "amount": round(amount, 6),
        "fee_burned": SEND_FEE,
        "tx_id": f"TX-{len(chain)}-{int(time.time())}",
        "thr_address": from_thr,
        "status": "pending"
    }

    pool = load_mempool()
    pool.append(tx)
    save_mempool(pool)

    update_last_block(tx, is_block=False)
    return jsonify(status="pending", tx=tx, new_balance_from=ledger[from_thr]), 200


# ─── ADMIN WHITELIST + MIGRATION ───────────────────
@app.route("/admin/whitelist", methods=["GET"])
def admin_whitelist_page():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return "Forbidden (wrong or missing secret)", 403
    return render_template("admin_whitelist.html", admin_secret=secret)


@app.route("/admin/whitelist/add", methods=["POST"])
def admin_whitelist_add():
    data = request.get_json() or {}
    if data.get("secret") != ADMIN_SECRET:
        return jsonify(error="forbidden"), 403

    btc = (data.get("btc_address") or "").strip()
    if not btc:
        return jsonify(error="missing_btc_address"), 400

    wl = load_json(WHITELIST_FILE, [])
    if btc not in wl:
        wl.append(btc)
        save_json(WHITELIST_FILE, wl)

    return jsonify(status="ok", whitelist=wl), 200


@app.route("/admin/whitelist/list", methods=["GET"])
def admin_whitelist_list():
    secret = request.args.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify(error="forbidden"), 403

    wl = load_json(WHITELIST_FILE, [])
    return jsonify(whitelist=wl), 200


@app.route("/admin/migrate_seeds", methods=["POST", "GET"])
def admin_migrate_seeds():
    payload = request.get_json() or {}
    secret = request.args.get("secret", "") or payload.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify(error="forbidden"), 403

    pledges = load_json(PLEDGE_CHAIN, [])
    changed = []

    for p in pledges:
        if p.get("send_seed_hash") and p.get("send_auth_hash"):
            continue

        thr_addr = p["thr_address"]
        btc_address = p["btc_address"]
        pledge_text = p["pledge_text"]
        pledge_hash = p["pledge_hash"]

        send_seed = secrets.token_hex(16)
        send_seed_hash = hashlib.sha256(send_seed.encode()).hexdigest()
        send_auth_hash = hashlib.sha256(f"{send_seed}:auth".encode()).hexdigest()

        p["send_seed_hash"] = send_seed_hash
        p["send_auth_hash"] = send_auth_hash
        p["has_passphrase"] = False

        chain = load_json(CHAIN_FILE, [])
        height = len(chain)

        pdf_name = create_secure_pdf_contract(
            btc_address=btc_address,
            pledge_text=pledge_text,
            thr_address=thr_addr,
            pledge_hash=pledge_hash,
            height=height,
            send_seed=send_seed,
            output_dir=CONTRACTS_DIR,
        )
        p["pdf_filename"] = pdf_name

        changed.append(
            {
                "thr_address": thr_addr,
                "btc_address": btc_address,
                "send_seed": send_seed,
                "pdf_filename": pdf_name,
            }
        )

    save_json(PLEDGE_CHAIN, pledges)
    return jsonify(migrated=changed), 200


# ─── MINING ENDPOINT ───────────────────────────────
@app.route("/submit_block", methods=["POST"])
def submit_block():
    """
    Accepts PoW submissions from miners.
    Supports both Legacy (String) and Stratum (SHA256d Header).
    Includes mempool TXs into the new block (simple FIFO).
    """
    data = request.get_json() or {}

    thr_address = data.get("thr_address")
    nonce = data.get("nonce")
    if not thr_address or nonce is None:
        return jsonify(error="Missing mining data"), 400

    chain = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    server_last_hash = blocks[-1].get("block_hash", "") if blocks else "0"*64

    is_stratum = "merkle_root" in data
    pow_hash = ""
    prev_hash = ""

    if is_stratum:
        merkle_root = data.get("merkle_root")
        prev_hash = data.get("prev_hash")
        time_val = data.get("time")
        nbits = data.get("nbits")
        version = data.get("version", 1)
        if not all([merkle_root, prev_hash, time_val, nbits]):
            return jsonify(error="Missing Stratum fields"), 400
        if prev_hash != server_last_hash:
            return jsonify(error="Stale block (prev_hash mismatch)"), 400

        try:
            header = struct.pack("<I", version)
            header += bytes.fromhex(prev_hash)[::-1]
            header += bytes.fromhex(merkle_root)[::-1]
            header += struct.pack("<I", time_val)
            header += struct.pack("<I", nbits)
            header += struct.pack("<I", nonce)
            pow_hash = sha256d(header)[::-1].hex()
        except Exception as e:
            return jsonify(error=f"Header construction failed: {e}"), 400

    else:
        pow_hash = data.get("pow_hash")
        prev_hash = data.get("prev_hash")
        if prev_hash != server_last_hash:
            return jsonify(error="Stale block (prev_hash mismatch)"), 400
        check = hashlib.sha256((prev_hash + thr_address).encode() + str(nonce).encode()).hexdigest()
        if check != pow_hash:
            return jsonify(error="Invalid hash calculation"), 400

    current_target = get_mining_target()
    if int(pow_hash, 16) > current_target:
        return jsonify(error=f"Insufficient difficulty. Target: {hex(current_target)}"), 400

    # Reward 80/10/10
    height = len(chain)
    total_reward = calculate_reward(height)
    miner_share = round(total_reward * 0.80, 6)
    ai_share    = round(total_reward * 0.10, 6)
    burn_share  = round(total_reward * 0.10, 6)

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    new_block = {
        "thr_address": thr_address,
        "timestamp": ts,
        "block_hash": pow_hash,
        "prev_hash": prev_hash,
        "nonce": nonce,
        "reward": total_reward,
        "reward_split": {"miner": miner_share, "ai": ai_share, "burn": burn_share},
        "pool_fee": burn_share,                      # for UI backward-compat
        "reward_to_miner": miner_share,              # for UI backward-compat
        "height": height,
        "type": "block",
        "target": current_target,
        "is_stratum": is_stratum
    }
    chain.append(new_block)

    # -------- include mempool TXs ----------
    pool = load_mempool()
    included = []
    if pool:
        # simple FIFO
        for tx in list(pool):
            tx["height"] = height
            tx["status"] = "confirmed"
            tx["timestamp"] = ts
            chain.append(tx)
            included.append(tx)
        # clear mempool
        save_mempool([])

        # ledger credit for receivers
        ledger = load_json(LEDGER_FILE, {})
        for tx in included:
            if tx.get("type") == "transfer":
                to_thr = tx["to"]
                amt = float(tx["amount"])
                fee = float(tx.get("fee_burned", 0.0))
                ledger[to_thr] = round(ledger.get(to_thr, 0.0) + amt, 6)
                # fee already deducted from sender, now we burn it
                ledger[BURN_ADDRESS] = round(ledger.get(BURN_ADDRESS, 0.0) + fee, 6)
        save_json(LEDGER_FILE, ledger)

    # -------- ledger reward split ----------
    ledger = load_json(LEDGER_FILE, {})
    ledger[thr_address] = round(ledger.get(thr_address, 0.0) + miner_share, 6)
    ledger[AI_WALLET_ADDRESS] = round(ledger.get(AI_WALLET_ADDRESS, 0.0) + ai_share, 6)
    ledger[BURN_ADDRESS] = round(ledger.get(BURN_ADDRESS, 0.0) + burn_share, 6)
    save_json(LEDGER_FILE, ledger)

    save_json(CHAIN_FILE, chain)
    update_last_block(new_block, is_block=True)

    print(f"⛏️ Miner {thr_address} found block #{height}! R={total_reward} (m/a/b: {miner_share}/{ai_share}/{burn_share}) | TXs: {len(included)} | Stratum={is_stratum}")
    return jsonify(status="accepted", height=height, reward=miner_share, tx_included=len(included)), 200


# ─── BACKGROUND MINTER ─────────────────────────────
def submit_mining_block_for_pledge(thr_addr):
    """
    Auto-mint REAL PoW block (legacy rule) + includes mempool TXs.
    Reward split 80/10/10 (burn=pool).
    """
    chain = load_json(CHAIN_FILE, [])
    pow_blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]

    if pow_blocks:
        prev_hash = pow_blocks[-1].get("block_hash", "0"*64)
        height = len(pow_blocks)
    else:
        prev_hash = "0"*64
        height = 0

    total_reward = calculate_reward(height)
    miner_share = round(total_reward * 0.80, 6)
    ai_share    = round(total_reward * 0.10, 6)
    burn_share  = round(total_reward * 0.10, 6)

    target = get_mining_target()
    nonce = random.randrange(0, 2**32)
    while True:
        h = hashlib.sha256((prev_hash + thr_addr).encode() + str(nonce).encode()).hexdigest()
        if int(h, 16) <= target:
            pow_hash = h
            break
        nonce = (nonce + 1) % (2**32)

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    new_block = {
        "thr_address": thr_addr,
        "timestamp": ts,
        "block_hash": pow_hash,
        "prev_hash": prev_hash,
        "nonce": nonce,
        "reward": total_reward,
        "reward_split": {"miner": miner_share, "ai": ai_share, "burn": burn_share},
        "pool_fee": burn_share,
        "reward_to_miner": miner_share,
        "height": height,
        "type": "block",
        "target": target,
        "is_stratum": False
    }
    chain.append(new_block)

    # include mempool TXs
    pool = load_mempool()
    included = []
    if pool:
        for tx in list(pool):
            tx["height"] = height
            tx["status"] = "confirmed"
            tx["timestamp"] = ts
            chain.append(tx)
            included.append(tx)
        save_mempool([])

        ledger = load_json(LEDGER_FILE, {})
        for tx in included:
            if tx.get("type") == "transfer":
                to_thr = tx["to"]
                amt = float(tx["amount"])
                fee = float(tx.get("fee_burned", 0.0))
                ledger[to_thr] = round(ledger.get(to_thr, 0.0) + amt, 6)
                ledger[BURN_ADDRESS] = round(ledger.get(BURN_ADDRESS, 0.0) + fee, 6)
        save_json(LEDGER_FILE, ledger)

    # reward split credit
    ledger = load_json(LEDGER_FILE, {})
    ledger[thr_addr] = round(ledger.get(thr_addr, 0.0) + miner_share, 6)
    ledger[AI_WALLET_ADDRESS] = round(ledger.get(AI_WALLET_ADDRESS, 0.0) + ai_share, 6)
    ledger[BURN_ADDRESS] = round(ledger.get(BURN_ADDRESS, 0.0) + burn_share, 6)
    save_json(LEDGER_FILE, ledger)

    save_json(CHAIN_FILE, chain)
    update_last_block(new_block, is_block=True)
    print(f"⛏️ [Pledge PoW] block #{height} for {thr_addr} | TXs: {len(included)} | hash={pow_hash[:16]}…")


def mint_first_blocks():
    pledges = load_json(PLEDGE_CHAIN, [])
    chain = load_json(CHAIN_FILE, [])
    seen = {
        b.get("thr_address")
        for b in chain
        if isinstance(b, dict) and b.get("thr_address")
    }

    for p in pledges:
        thr = p["thr_address"]
        if thr in seen:
            continue
        submit_mining_block_for_pledge(thr)


scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(mint_first_blocks, "interval", minutes=1)
scheduler.start()

# Run AI Wallet Check on Startup
ensure_ai_wallet()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3333))
    app.run(host="0.0.0.0", port=port)
