# server.py  (ThronosChain — Full, unified, quorum-enabled)
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
# - Mempool & 80/10/10 Reward Split (V3.7)
# - Quorum Attestations (BLS/MuSig2 placeholder) + aggregator job (V2.9)
# - AI Knowledge Blocks: ai_block_log.json -> mempool -> ai_knowledge TXs (V4.0)
# - AI Architect & Multi-Model Support (V3.6 Update)
# - Dynamic Fees & Burning (V4.1)
# - Swap / DeFi Interface (V4.2)
# - IoT Parking State (V4.3)
# - Crypto Hunters Game (V4.4)

import os, json, time, hashlib, logging, secrets, random, uuid, zipfile, io, struct, binascii
from datetime import datetime
from PIL import Image

import requests
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler

# ── Local modules
try:
    from phantom_gateway_mainnet import get_btc_txns
    from secure_pledge_embed import create_secure_pdf_contract
    from phantom_decode import decode_payload_from_image
    from ai_agent_service import ThronosAI
    # ── Quorum modules (placeholders μέχρι να μπει real crypto)
    from quorum_crypto import aggregate as qc_aggregate, verify as qc_verify
except ImportError as e:
    print(f"CRITICAL IMPORT ERROR: {e}")
    # Fallback mocks to prevent 500 on start if files missing
    get_btc_txns = lambda a,b: []
    create_secure_pdf_contract = lambda *args: "error.pdf"
    decode_payload_from_image = lambda *args: None
    class ThronosAI:
        def generate_response(self, *args, **kwargs): return {"response": "AI Service Unavailable", "status": "error"}
        def generate_quantum_key(self): return "mock_key"
    qc_aggregate = lambda *args: None
    qc_verify = lambda *args: False


# ─── CONFIG ────────────────────────────────────────
app = Flask(__name__)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

DATA_DIR   = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

LEDGER_FILE         = os.path.join(DATA_DIR, "ledger.json")
WBTC_LEDGER_FILE    = os.path.join(DATA_DIR, "wbtc_ledger.json")
CHAIN_FILE          = os.path.join(DATA_DIR, "phantom_tx_chain.json")
PLEDGE_CHAIN        = os.path.join(DATA_DIR, "pledge_chain.json")
LAST_BLOCK_FILE     = os.path.join(DATA_DIR, "last_block.json")
WHITELIST_FILE      = os.path.join(DATA_DIR, "free_pledge_whitelist.json")
AI_CREDS_FILE       = os.path.join(DATA_DIR, "ai_agent_credentials.json")
AI_BLOCK_LOG_FILE   = os.path.join(DATA_DIR, "ai_block_log.json")
WATCHER_LEDGER_FILE = os.path.join(DATA_DIR, "watcher_ledger.json")
IOT_DATA_FILE       = os.path.join(DATA_DIR, "iot_data.json")
IOT_PARKING_FILE    = os.path.join(DATA_DIR, "iot_parking.json")
MEMPOOL_FILE        = os.path.join(DATA_DIR, "mempool.json")
ATTEST_STORE_FILE   = os.path.join(DATA_DIR, "attest_store.json")

# AI commerce
AI_PACKS_FILE       = os.path.join(DATA_DIR, "ai_packs.json")
AI_CREDITS_FILE     = os.path.join(DATA_DIR, "ai_credits.json")

# AI extra storage
AI_FILES_DIR   = os.path.join(DATA_DIR, "ai_files")
AI_CORPUS_FILE = os.path.join(DATA_DIR, "ai_offline_corpus.json")
os.makedirs(AI_FILES_DIR, exist_ok=True)

# NEW: αποθήκευση sessions (λίστα συνομιλιών)
AI_SESSIONS_FILE = os.path.join(DATA_DIR, "ai_sessions.json")

ADMIN_SECRET   = os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW")

BTC_RECEIVER  = "1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ"
MIN_AMOUNT    = 0.00001

CONTRACTS_DIR = os.path.join(DATA_DIR, "contracts")
os.makedirs(CONTRACTS_DIR, exist_ok=True)

UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# --- Dynamic Fee Config ---
FEE_RATE = 0.005  # 0.5% burn rate
MIN_FEE  = 0.001  # Minimum fee in THR

# --- Mining Config ---
INITIAL_TARGET    = 2 ** 236         # 5 hex zeros (20 bits)
TARGET_BLOCK_TIME = 60               # seconds
RETARGET_INTERVAL = 10               # blocks

AI_WALLET_ADDRESS = os.getenv("THR_AI_AGENT_WALLET", "THR_AI_AGENT_WALLET_V1")
BURN_ADDRESS      = "0x0"
SWAP_POOL_ADDRESS = "THR_SWAP_POOL_V1"

# Πόσα blocks "έχουν ήδη γίνει" πριν ξεκινήσει το τρέχον chain αρχείο
HEIGHT_OFFSET = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("thronos")

# Initialize AI
try:
    ai_agent = ThronosAI()
except Exception as e:
    print(f"AI Init Error: {e}")
    ai_agent = None


# ─── HELPERS ───────────────────────────────────────
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_mempool():
    return load_json(MEMPOOL_FILE, [])

def save_mempool(pool):
    save_json(MEMPOOL_FILE, pool)

def load_attest_store():
    return load_json(ATTEST_STORE_FILE, {})

def save_attest_store(store):
    save_json(ATTEST_STORE_FILE, store)

def calculate_dynamic_fee(amount: float) -> float:
    """
    Calculates the burn fee based on the amount.
    Fee = Max(MIN_FEE, amount * FEE_RATE)
    """
    return round(max(MIN_FEE, amount * FEE_RATE), 6)

# --- AI Packs & Credits helpers ------------------------------------------------

AI_DEFAULT_PACKS = [
    {
        "code": "Q-100",
        "title": "Quantum Explorer 100",
        "description": "Για light χρήση, tests και μικρά prompts.",
        "credits": 100,
        "price_thr": 5.0,
    },
    {
        "code": "Q-500",
        "title": "Researcher 500",
        "description": "Σταθερή καθημερινή χρήση του Quantum Chat.",
        "credits": 500,
        "price_thr": 20.0,
    },
    {
        "code": "Q-2000",
        "title": "Validator 2000",
        "description": "Για power-users, devs και validators του Thronos.",
        "credits": 2000,
        "price_thr": 60.0,
    },
]

# Πόσα credits καίει κάθε AI μήνυμα
AI_CREDIT_COST_PER_MSG = int(os.getenv("AI_CREDIT_COST_PER_MSG", "1"))

def load_ai_packs():
    """Διαβάζει τα διαθέσιμα packs από αρχείο, αλλιώς επιστρέφει τα default."""
    data = load_json(AI_PACKS_FILE, None)
    if isinstance(data, list) and data:
        return data
    return AI_DEFAULT_PACKS


def save_ai_packs(packs):
    """Αν θες κάποια στιγμή να αλλάζεις δυναμικά τα packs."""
    save_json(AI_PACKS_FILE, packs)


def load_ai_credits():
    """wallet -> σύνολο credits"""
    return load_json(AI_CREDITS_FILE, {})


def save_ai_credits(credits):
    save_json(AI_CREDITS_FILE, credits)

def load_ai_sessions():
    return load_json(AI_SESSIONS_FILE, [])

def save_ai_sessions(sessions):
    save_json(AI_SESSIONS_FILE, sessions)

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def target_to_bits(target: int) -> int:
    if target == 0:
        return 0
    target_hex = hex(target)[2:]
    if len(target_hex) % 2 != 0:
        target_hex = "0" + target_hex
    target_bytes = bytes.fromhex(target_hex)
    if target_bytes[0] >= 0x80:
        target_bytes = b"\\x00" + target_bytes
    exponent = len(target_bytes)
    coefficient = target_bytes[:3]
    if len(coefficient) < 3:
        coefficient = coefficient + b"\\x00" * (3 - len(coefficient))
    return (exponent << 24) | int.from_bytes(coefficient, "big")

def calculate_reward(height: int) -> float:
    halvings = height // 210000
    if halvings > 9:
        return 0.0
    return round(1.0 / (2 ** halvings), 6)

def recompute_height_offset_from_ledger():
    """
    Διαβάζει ledger + chain και βρίσκει πόσα THR έχουν εκδοθεί
    ΠΡΙΝ αρχίσουν να γράφονται blocks στο phantom_tx_chain.json.

    Το μεταφράζει σε ισοδύναμο αριθμό blocks σύμφωνα με
    το halving schedule (1.0, 0.5, 0.25, …).
    """
    global HEIGHT_OFFSET

    ledger = load_json(LEDGER_FILE, {})
    chain  = load_json(CHAIN_FILE, [])

    # Όσα blocks υπάρχουν ΗΔΗ στο chain
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    minted_from_blocks = sum(float(b.get("reward", 0.0)) for b in blocks)

    # Συνολικό supply από ledger (άθροισμα όλων των διευθύνσεων)
    total_ledger = sum(float(v) for v in ledger.values())

    # Ό,τι περισσεύει το θεωρούμε "παλιό supply χωρίς blocks"
    pre_mined = max(0.0, total_ledger - minted_from_blocks)

    if pre_mined <= 0:
        HEIGHT_OFFSET = 0
        logger.info("No pre-mined supply detected. HEIGHT_OFFSET = 0")
        return

    remaining = pre_mined
    h = 0
    # Μέχρι max ~2.1M blocks, δεν μας νοιάζει απόδοση, είναι startup-only
    while remaining > 0 and h < 2_100_000:
        r = calculate_reward(h)
        if r <= 0:
            break
        remaining -= r
        h += 1

    HEIGHT_OFFSET = h
    logger.info(
        f"[SUPPLY] Pre-mined ≈ {pre_mined:.6f} THR -> HEIGHT_OFFSET = {HEIGHT_OFFSET}"
    )


def update_last_block(entry, is_block=True):
    """
    Γράφει last_block.json αλλά πλέον κρατά και:
    - block_count (με offset)
    - total_supply (άθροισμα ledger)
    ώστε η αρχική σελίδα να ξέρει ΠΟΣΑ block και ΠΟΣΟ supply έχουμε.
    """
    chain  = load_json(CHAIN_FILE, [])
    ledger = load_json(LEDGER_FILE, {})

    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    block_count = HEIGHT_OFFSET + len(blocks)

    total_supply = round(sum(float(v) for v in ledger.values()), 6)

    summary = {
        "height":     entry.get("height"),
        "block_hash": entry.get("block_hash") or entry.get("tx_id"),
        "timestamp":  entry.get("timestamp"),
        "thr_address": entry.get("thr_address"),
        "type": "block" if is_block else entry.get("type", "transfer"),
        "block_count": block_count,
        "total_supply": total_supply,
    }
    save_json(LAST_BLOCK_FILE, summary)

def verify_btc_payment(btc_address, min_amount=MIN_AMOUNT):
    try:
        txns = get_btc_txns(btc_address, BTC_RECEIVER)
        paid = any(tx["to"] == BTC_RECEIVER and tx["amount_btc"] >= min_amount for tx in txns)
        return paid, txns
    except Exception as e:
        logger.error(f"Watcher Error: {e}")
        return False, []

def get_mining_target():
    chain  = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    if len(blocks) < RETARGET_INTERVAL:
        return INITIAL_TARGET
    last_block  = blocks[-1]
    last_target = int(last_block.get("target", INITIAL_TARGET))
    if len(blocks) % RETARGET_INTERVAL != 0:
        return last_target
    start_block = blocks[-RETARGET_INTERVAL]
    try:
        t_fmt = "%Y-%m-%d %H:%M:%S UTC"
        t_end = datetime.strptime(last_block["timestamp"], t_fmt).timestamp()
        t_sta = datetime.strptime(start_block["timestamp"], t_fmt).timestamp()
    except Exception as e:
        logger.error(f"Time parse error: {e}")
        return last_target
    actual = max(1, t_end - t_sta)
    expected = RETARGET_INTERVAL * TARGET_BLOCK_TIME
    ratio = actual / expected
    ratio = 0.25 if ratio < 0.25 else (4.0 if ratio > 4.0 else ratio)
    new_target = int(last_target * ratio)
    if new_target > INITIAL_TARGET:
        new_target = INITIAL_TARGET
    return new_target


# ─── AI FILE / CORPUS HELPERS ──────────────────────
def extract_ai_files_from_text(full_text: str):
    """
    Ψάχνει για blocks τύπου:
      [[FILE:filename.ext]]
      ...περιεχόμενο...
      [[/FILE]]
    Γράφει τα αρχεία στο AI_FILES_DIR και επιστρέφει:
      files: list[ {filename, path, size} ]
      cleaned_text: text χωρίς τα raw blocks.
    """
    files = []
    cleaned_parts = []
    i = 0
    while True:
        start = full_text.find("[[FILE:", i)
        if start == -1:
            cleaned_parts.append(full_text[i:])
            break

        # ό,τι υπάρχει πριν το block
        cleaned_parts.append(full_text[i:start])

        end_name = full_text.find("]]", start)
        if end_name == -1:
            # δεν κλείνει σωστά, κρατάμε όλο το υπόλοιπο
            cleaned_parts.append(full_text[start:])
            break

        filename = full_text[start + len("[[FILE:"):end_name].strip()
        end_block = full_text.find("[[/FILE]]", end_name)
        if end_block == -1:
            cleaned_parts.append(full_text[start:])
            break

        content = full_text[end_name + 2:end_block]

        # ασφαλές όνομα αρχείου
        safe_name = filename.replace("..", "_").replace("/", "_").replace("\\", "_")
        file_path = os.path.join(AI_FILES_DIR, safe_name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content.strip())
            size = len(content.encode("utf-8"))
            files.append({
                "filename": safe_name,
                "path": file_path,
                "size": size,
            })
            cleaned_parts.append(f"\\n[AI file generated: {safe_name}]\\n")
        except Exception as e:
            print("AI file write error:", e)
            cleaned_parts.append(f"\\n[AI file error: {safe_name}]\\n")

        i = end_block + len("[[/FILE]]")

    cleaned_text = "".join(cleaned_parts).strip()
    return files, cleaned_text


def enqueue_offline_corpus(wallet: str, prompt: str, response: str, files, session_id: str | None = None):
    """
    Ελαφρύ offline corpus για Whisper / training + sessions.
    Κρατάμε και session_id ώστε να χωρίζονται οι συνομιλίες τύπου ChatGPT.
    """
    sid = session_id or "default"

    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    entry = {
        "timestamp": ts,
        "wallet": wallet or "",
        "prompt": prompt,
        "response": response,
        "files": [f.get("filename") for f in files] if files else [],
        "session_id": sid,
    }

    corpus = load_json(AI_CORPUS_FILE, [])
    corpus.append(entry)
    corpus = corpus[-1000:]
    save_json(AI_CORPUS_FILE, corpus)

    # update / create session meta
    if wallet:
        sessions = load_ai_sessions()
        found = None
        for s in sessions:
            if s.get("wallet") == wallet and s.get("id") == sid:
                found = s
                break

        if not found:
            title_src = prompt.strip() or "Νέα συνομιλία"
            title = (title_src.replace("\\n", " ")[:80]).strip()
            found = {
                "id": sid,
                "wallet": wallet,
                "title": title or "Νέα συνομιλία",
                "created_at": ts,
                "updated_at": ts,
            }
            sessions.append(found)
        else:
            found["updated_at"] = ts

        save_ai_sessions(sessions)


# ─── VIEWER HELPERS ────────────────────────────────
def get_blocks_for_viewer():
    chain = load_json(CHAIN_FILE, [])
    raw_blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    blocks = []
    for b in raw_blocks:
        height = b.get("height")
        if height is None:
            height = len(blocks)
        block_txs = [
            tx for tx in chain
            if tx.get("type") in ("transfer", "coinbase", "service_payment", "ai_knowledge")
            and tx.get("height") == height
        ]
        rsplit = b.get("reward_split") or {}
        reward_to_miner = float(rsplit.get("miner", b.get("reward_to_miner", 0.0)))
        reward_to_ai    = float(rsplit.get("ai", 0.0))
        burn_from_split = float(rsplit.get("burn", 0.0))
        fees_from_txs   = sum(float(tx.get("fee_burned", 0.0)) for tx in block_txs)
        blocks.append({
            "index": height,
            "hash": b.get("block_hash",""),
            "fee_burned": round(burn_from_split + fees_from_txs, 6),
            "reward_to_miner": reward_to_miner,
            "reward_to_ai": reward_to_ai,
            "is_stratum": bool(b.get("is_stratum")),
            "nonce": b.get("nonce","-"),
            "transactions": block_txs,
            "timestamp": b.get("timestamp","")
        })
    blocks.sort(key=lambda x: x["index"], reverse=True)
    return blocks

def get_transactions_for_viewer():
    chain = load_json(CHAIN_FILE, [])
    pool  = load_mempool()

    # Confirmed txs από το chain
    chain_txs = [
        t for t in chain
        if isinstance(t, dict)
        and t.get("type") in ["transfer", "service_payment", "ai_knowledge", "coinbase", "game_reward"]
    ]

    # Pending από mempool (χωρίς height)
    pending_txs = [
        t for t in pool
        if isinstance(t, dict)
        and t.get("type") in ["transfer", "service_payment", "ai_knowledge", "game_reward"]
    ]

    all_txs = chain_txs + pending_txs

    out = []
    for t in all_txs:
        preview = ""
        if t.get("type") == "ai_knowledge":
            payload = t.get("ai_payload") or ""
            preview = payload[:96]

        tx_type = t.get("type", "transfer")
        tx_from = t.get("from", "Unknown")
        tx_to   = t.get("to",   "Unknown")
        height  = t.get("height")  # μπορεί να είναι None για pending
        fee     = t.get("fee_burned", 0.0)

        tx_id = t.get("tx_id")
        if not tx_id and tx_type == "coinbase":
            tx_id = f"COINBASE-{height}"

        out.append({
            "tx_id":     tx_id or "N/A",
            "height":    height,
            "from":      tx_from,
            "to":        tx_to,
            "amount":    t.get("amount", 0.0),
            "fee":       fee,
            "timestamp": t.get("timestamp", ""),
            "type":      tx_type,
            "note":      preview,
        })

    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out


def ensure_ai_wallet():
    pledges = load_json(PLEDGE_CHAIN, [])
    ai_pledge = next((p for p in pledges if p.get("thr_address")==AI_WALLET_ADDRESS), None)
    if ai_pledge: 
        print(f"🤖 AI Wallet {AI_WALLET_ADDRESS} ready.")
        return
    print(f"🤖 Initializing AI Agent Wallet: {AI_WALLET_ADDRESS}")
    send_seed      = secrets.token_hex(16)
    send_seed_hash = hashlib.sha256(send_seed.encode()).hexdigest()
    send_auth_hash = hashlib.sha256(f"{send_seed}:auth".encode()).hexdigest()
    new_pledge = {
        "btc_address":"SYSTEM_AI_RESERVE",
        "pledge_text":"Thronos AI Agent Genesis Allocation",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "pledge_hash":"AI_GENESIS_"+secrets.token_hex(8),
        "thr_address":AI_WALLET_ADDRESS,
        "send_seed_hash":send_seed_hash,
        "send_auth_hash":send_auth_hash,
        "has_passphrase":False,
        "is_system":True
    }
    pledges.append(new_pledge)
    save_json(PLEDGE_CHAIN, pledges)
    creds = {
        "thr_address":AI_WALLET_ADDRESS,
        "auth_secret":send_seed,
        "note":"Put these in ai_agent/agent_config.json"
    }
    save_json(AI_CREDS_FILE, creds)
    print(f"✅ AI Wallet Registered. Credentials saved to {AI_CREDS_FILE}")


def decode_iot_steganography(image_path):
    try:
        img = Image.open(image_path)
        width, height = img.size
        pixels = img.load()
        delimiter = "###END###"
        chars=[]
        cur=""
        for y in range(height):
            for x in range(width):
                r,g,b = pixels[x,y]
                for val in (r,g,b):
                    cur += str(val & 1)
                    if len(cur)==8:
                        chars.append(chr(int(cur,2)))
                        cur=""
                        if len(chars)>=len(delimiter) and "".join(chars[-len(delimiter):])==delimiter:
                            json_str = "".join(chars[:-len(delimiter)])
                            return json.loads(json_str)
        return None
    except Exception as e:
        print("Stego Decode Error:", e)
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
    return render_template(
        "thronos_block_viewer.html",
        blocks=get_blocks_for_viewer(),
        transactions=get_transactions_for_viewer(),
    )

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

# NEW service pages
@app.route("/bridge")
def bridge_page():
    return render_template("bridge.html")

@app.route("/iot")
def iot_page():
    return render_template("iot.html")

@app.route("/chat")
def chat_page():
    return render_template("chat.html")

@app.route("/swap")
def swap_page():
    return render_template("swap.html")

@app.route("/gateway")
def gateway_page():
    return render_template("gateway.html")

@app.route("/ai_packs")
def ai_packs_page():
    return render_template("ai_packs.html")

@app.route("/game")
def game_page():
    return render_template("game.html")

# ─── AI ARCHITECT ROUTES (NEW) ──────────────────────────────────────────────

@app.route("/architect")
def architect_page():
    return render_template("architect.html")

@app.route("/api/ai_blueprints")
def api_ai_blueprints():
    """
    Returns list of available blueprints from data/ai_blueprints/
    """
    bp_dir = os.path.join(DATA_DIR, "ai_blueprints")
    if not os.path.exists(bp_dir):
        os.makedirs(bp_dir, exist_ok=True)
    
    blueprints = []
    try:
        for f in os.listdir(bp_dir):
            if f.endswith(".md") or f.endswith(".txt"):
                blueprints.append(f)
    except Exception as e:
        print("Error listing blueprints:", e)
        
    # Sort for consistency
    blueprints.sort()
    return jsonify({"blueprints": blueprints}), 200

@app.route("/api/architect_generate", methods=["POST"])
def api_architect_generate():
    """
    Thronos AI Architect:
    - Generates full project implementation based on blueprint + specs.
    - Returns [[FILE:...]] blocks.
    - Writes files to AI_FILES_DIR.
    """
    if not ai_agent:
        return jsonify(error="AI Agent not available"), 503

    data = request.get_json() or {}
    wallet      = (data.get("wallet") or "").strip()
    session_id  = (data.get("session_id") or "").strip() or None
    blueprint   = (data.get("blueprint") or "").strip()
    project_spec = (data.get("spec") or data.get("specs") or "").strip() # Handle both keys just in case
    model_key   = (data.get("model") or data.get("model_key") or "gpt-4o").strip()

    if not blueprint or not project_spec:
        return jsonify(error="Missing blueprint or spec"), 400

    # Load blueprint
    bp_path = os.path.join(DATA_DIR, "ai_blueprints", blueprint)
    if not os.path.exists(bp_path):
        # Fallback: try to find it in the list if passed as name only
        bp_dir = os.path.join(DATA_DIR, "ai_blueprints")
        found = False
        if os.path.exists(bp_dir):
            for f in os.listdir(bp_dir):
                if f == blueprint:
                    bp_path = os.path.join(bp_dir, f)
                    found = True
                    break
        if not found:
             return jsonify(error="Blueprint not found"), 404

    try:
        with open(bp_path, "r", encoding="utf-8") as f:
            bp_text = f.read()
    except Exception as e:
        return jsonify(error=f"Cannot read blueprint: {e}"), 500

    # New FULL IMPLEMENTATION prompt
    prompt = (
        "Είσαι ο Κύριος Αρχιτέκτονας του Thronos.\\n"
        "Χτίζεις ΠΛΗΡΗ software projects (όχι μόνο skeletons).\\n"
        "Για κάθε αρχείο που παράγεις, γράφεις όσο πιο ολοκληρωμένο, λειτουργικό κώδικα γίνεται.\\n"
        "- Π.χ. αν υπάρχει login page, υλοποίησε πλήρη φόρμα, validation και fake auth flow.\\n"
        "- Αν υπάρχει API route, γράψε πλήρες handler με όλα τα πεδία.\\n"
        "- Αν υπάρχει API route, γράψε πλήρες handler με όλα τα πεδία.\\n"
        "- Αν υπάρχει database layer, βάλε πλήρη μοντέλα / helpers.\\n\\n"
        "ΠΡΟΤΥΠΟ ΕΞΟΔΟΥ:\\n"
        "Πρέπει να απαντάς ΜΟΝΟ με blocks της μορφής:\\n"
        "[[FILE:path/filename.ext]]\\n"
        "...περιεχόμενο αρχείου...\\n"
        "[[/FILE]]\\n\\n"
        "Μην εξηγήσεις, μην προσθέσεις κείμενο εκτός αρχείων.\\n\\n"
        "BLUEPRINT:\\n"
        f"{bp_text}\\n\\n"
        "PROJECT SPEC (τι θέλει ο χρήστης):\\n"
        f"{project_spec}\\n\\n"
        "Χτίσε ΟΛΑ τα βασικά αρχεία του project με ΠΛΗΡΗ υλοποίηση, όχι απλό σκελετό."
    )

    # Call AI
    # Note: server.py uses 'ai_agent' global instance
    # Pass session_id to maintain context if needed (though architect usually is one-shot, 
    # but user might refine in same session)
    raw = ai_agent.generate_response(prompt, wallet=wallet, model_key=model_key, session_id=session_id)

    if isinstance(raw, dict):
        full_text   = str(raw.get("response") or "")
        quantum_key = raw.get("quantum_key") or ai_agent.generate_quantum_key()
        status      = raw.get("status", "architect")
    else:
        full_text   = str(raw)
        quantum_key = ai_agent.generate_quantum_key()
        status      = "architect"

    # Extract files
    try:
        files, cleaned = extract_ai_files_from_text(full_text)
    except Exception as e:
        print("Architect file extraction error:", e)
        files = []
        cleaned = full_text

    # Log to corpus
    try:
        title = f"[ARCHITECT:{blueprint}] {project_spec[:80]}"
        enqueue_offline_corpus(wallet, title, full_text, files, session_id=session_id)
    except Exception as e:
        print("architect corpus error:", e)

    return jsonify({
        "status": status,
        "quantum_key": quantum_key,
        "blueprint": blueprint,
        "response": cleaned,
        "files": [
            {
                "filename": f.get("filename"),
                "size": f.get("size")
            } for f in (files or [])
        ],
        "session_id": session_id,
    }), 200

# ─── RECOVERY FLOW ─────────────────────────────────
@app.route("/recovery")
def recovery_page():
    return render_template("recovery.html")

@app.route("/recover_submit", methods=["POST"])
def recover_submit():
    if "file" not in request.files:
        return jsonify(error="No file part"), 400
    file = request.files["file"]
    passphrase = request.form.get("passphrase","").strip()
    if file.filename=="":
        return jsonify(error="No selected file"), 400
    if not passphrase:
        return jsonify(error="Passphrase is required"), 400
    filename = secure_filename(file.filename)
    temp_path = os.path.join(DATA_DIR, f"temp_{int(time.time())}_{filename}")
    try:
        file.save(temp_path)
        payload = decode_payload_from_image(temp_path, passphrase)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if payload:
            return jsonify(status="success", payload=payload), 200
        return jsonify(error="Failed to decode or decrypt."), 400
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify(error=f"Server error: {str(e)}"), 500


# ─── STATUS APIs ───────────────────────────────────
@app.route("/chain")
def get_chain():
    return jsonify(load_json(CHAIN_FILE, [])), 200

@app.route("/last_block")
def api_last_block():
    return jsonify(load_json(LAST_BLOCK_FILE, {})), 200

@app.route("/last_block_hash")
def last_block_hash():
    chain  = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    if blocks:
        last = blocks[-1]
        global_height = HEIGHT_OFFSET + len(blocks) - 1
        return jsonify(
            last_hash=last.get("block_hash", ""),
            height=global_height,
            timestamp=last.get("timestamp"),
        )
    return jsonify(last_hash="0"*64, height=-1, timestamp=None)

@app.route("/mining_info")
def mining_info():
    target = get_mining_target()
    nbits  = target_to_bits(target)

    chain  = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]

    last_hash = blocks[-1].get("block_hash", "") if blocks else "0" * 64

    local_height   = len(blocks)               # πόσα blocks έχουμε στο αρχείο
    global_height  = HEIGHT_OFFSET + local_height  # block height με το offset
    reward         = calculate_reward(global_height)

    mempool_len = len(load_mempool())

    return jsonify({
        "target":        hex(target),
        "nbits":         hex(nbits),
        "difficulty_int": int(INITIAL_TARGET // target),
        "reward":        reward,
        "height":        global_height,
        "local_height":  local_height,
        "last_hash":     last_hash,
        "mempool":       mempool_len,
    }), 200

@app.route("/api/network_stats")
def network_stats():
    pledges = load_json(PLEDGE_CHAIN, [])
    chain   = load_json(CHAIN_FILE, [])
    ledger  = load_json(LEDGER_FILE, {})

    pledge_count = len(pledges)

    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    block_count = HEIGHT_OFFSET + len(blocks)

    tx_count = len([
        t for t in chain
        if isinstance(t, dict) and t.get("type") in ("transfer", "service_payment", "ai_knowledge", "coinbase")
    ])

    burned     = float(ledger.get(BURN_ADDRESS, 0))
    ai_balance = float(ledger.get(AI_WALLET_ADDRESS, 0))
    total_supply = round(sum(float(v) for v in ledger.values()), 6)

    # pledge growth όπως πριν
    pledge_dates = {}
    for p in pledges:
        ts = p.get("timestamp", "").split(" ")[0]
        if not ts:
            continue
        pledge_dates[ts] = pledge_dates.get(ts, 0) + 1

    sorted_dates = sorted(pledge_dates.keys())
    cumulative   = []
    run = 0
    for d in sorted_dates:
        run += pledge_dates[d]
        cumulative.append({"date": d, "count": run})

    return jsonify({
        "pledge_count": pledge_count,
        "block_count":  block_count,
        "tx_count":     tx_count,
        "burned":       burned,
        "ai_balance":   ai_balance,
        "total_supply": total_supply,
        "pledge_growth": cumulative,
    })

@app.route("/api/network_live")
def network_live():
    chain  = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    mempool_len = len(load_mempool())

    window = 20
    avg_time = None
    if len(blocks) >= 2:
        tail = blocks[-min(window, len(blocks)):]
        try:
            t_fmt = "%Y-%m-%d %H:%M:%S UTC"
            t0 = datetime.strptime(tail[0]["timestamp"], t_fmt).timestamp()
            t1 = datetime.strptime(tail[-1]["timestamp"], t_fmt).timestamp()
            avg_time = (t1 - t0) / max(1, (len(tail) - 1))
        except Exception:
            avg_time = None

    target     = get_mining_target()
    difficulty = int(INITIAL_TARGET // target)
    hashrate   = None
    if avg_time and avg_time > 0:
        hashrate = int(difficulty * (2**32) / avg_time)

    block_count = HEIGHT_OFFSET + len(blocks)

    return jsonify({
        "difficulty":          difficulty,
        "avg_block_time_sec":  avg_time,
        "est_hashrate_hs":     hashrate,
        "block_count":         block_count,
        "tx_count":            len(chain),
        "mempool":             mempool_len,
    })

@app.route("/api/mempool")
def api_mempool():
    return jsonify(load_mempool()), 200

@app.route("/api/blocks")
def api_blocks():
    return jsonify(get_blocks_for_viewer()), 200


# ─── NEW SERVICES APIs ─────────────────────────────
@app.route("/api/bridge/data")
def bridge_data():
    return jsonify(load_json(WATCHER_LEDGER_FILE, [])), 200

@app.route("/api/iot/data")
def iot_data():
    data = load_json(IOT_DATA_FILE, [])
    return jsonify(data if data else []), 200

@app.route("/api/iot/submit", methods=["POST"])
def iot_submit():
    if "file" not in request.files:
        return jsonify(error="No file uploaded"), 400
    file = request.files["file"]
    if file.filename=="":
        return jsonify(error="No file selected"), 400
    try:
        filename=secure_filename(file.filename)
        temp_path=os.path.join(UPLOADS_DIR,f"iot_temp_{int(time.time())}_{filename}")
        file.save(temp_path)
        data=decode_iot_steganography(temp_path)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if not data:
            return jsonify(error="Failed to decode steganography"),400
        if "vehicle_id" not in data:
            return jsonify(error="Invalid data format"),400
        iot_list=load_json(IOT_DATA_FILE,[])
        iot_list=[v for v in iot_list if v.get("vehicle_id")!=data["vehicle_id"]]
        iot_list.append(data)
        if len(iot_list)>100:
            iot_list=iot_list[-100:]
        save_json(IOT_DATA_FILE,iot_list)
        print(f"🚗 IoT Update: {data['vehicle_id']} | Odo: {data.get('odometer')}")
        return jsonify(status="success", vehicle_id=data["vehicle_id"]),200
    except Exception as e:
        print("IoT Submit Error:",e)
        return jsonify(error=str(e)),500

@app.route("/api/iot/autonomous_request", methods=["POST"])
def iot_autonomous_request():
    data = request.get_json() or {}
    wallet = data.get("wallet")
    amount = data.get("amount",0)
    if not wallet or amount<=0:
        return jsonify(status="denied",message="Invalid request"),400
    ledger=load_json(LEDGER_FILE,{})
    balance=float(ledger.get(wallet,0.0))
    if balance<amount:
        return jsonify(status="denied",message="Insufficient THR funds"),400
    ledger[wallet]=round(balance-amount,6)
    ledger[AI_WALLET_ADDRESS]=round(ledger.get(AI_WALLET_ADDRESS,0.0)+amount,6)
    save_json(LEDGER_FILE,ledger)
    chain=load_json(CHAIN_FILE,[])
    tx={
        "type":"service_payment",
        "service":"AI_AUTOPILOT",
        "from":wallet,
        "to":AI_WALLET_ADDRESS,
        "amount":amount,
        "timestamp":time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id":f"SRV-{len(chain)}-{int(time.time())}"
    }
    chain.append(tx)
    save_json(CHAIN_FILE,chain)
    update_last_block(tx,is_block=False)
    print(f"🤖 AI Autopilot Activated for {wallet}. Payment: {amount} THR")
    return jsonify(status="granted", message="AI Driver Activated"),200

# ─── IOT PARKING API (NEW) ─────────────────────────
@app.route("/api/iot/parking", methods=["GET"])
def api_iot_parking():
    """
    Returns the current state of parking spots.
    If file doesn't exist, init with random data.
    """
    if not os.path.exists(IOT_PARKING_FILE):
        # Init random spots
        spots = []
        for i in range(12):
            spots.append({
                "id": f"P-{101+i}",
                "status": "free" if random.random() > 0.3 else "occupied",
                "reservedBy": None
            })
        save_json(IOT_PARKING_FILE, spots)
    
    return jsonify(load_json(IOT_PARKING_FILE, [])), 200

@app.route("/api/iot/reserve", methods=["POST"])
def api_iot_reserve():
    """
    Reserves a spot. Requires payment (handled via send_thr logic usually, 
    but here we can just update state if payment verified or trust client for MVP simulation).
    Ideally, client calls send_thr, then calls this with tx_id to prove payment.
    For simplicity/simulation, we just update state.
    """
    data = request.get_json() or {}
    spot_id = data.get("spot_id")
    wallet = data.get("wallet")
    
    if not spot_id or not wallet:
        return jsonify(error="Missing fields"), 400
        
    spots = load_json(IOT_PARKING_FILE, [])
    found = False
    for s in spots:
        if s["id"] == spot_id:
            if s["status"] != "free":
                return jsonify(error="Spot not free"), 400
            s["status"] = "reserved"
            s["reservedBy"] = wallet
            found = True
            break
            
    if found:
        save_json(IOT_PARKING_FILE, spots)
        return jsonify(status="success"), 200
    else:
        return jsonify(error="Spot not found"), 404


# ─── QUANTUM CHAT API (ενιαίο AI + αρχεία + offline corpus) ─────────────────
@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Unified AI chat endpoint με credits + sessions.

    - Αν ο χρήστης έχει δηλώσει wallet, καίει AI credits από το ai_credits.json
    - Αν δεν έχει wallet, δουλεύει ως demo (infinite)
    - Αν έχει wallet αλλά 0 credits, δεν προχωρά σε κλήση AI
    - Κάθε μήνυμα γράφεται στο ai_offline_corpus.json με session_id
    """
    if not ai_agent:
        return jsonify(error="AI Agent not available"), 503

    data = request.get_json() or {}
    msg = (data.get("message") or "").strip()
    wallet = (data.get("wallet") or "").strip()
    session_id = (data.get("session_id") or "").strip() or None
    model_key = (data.get("model_key") or "").strip() or None  # <--- NEW

    if not msg:
        return jsonify(error="Message required"), 400

    # --- Credits check (μόνο αν έχουμε wallet) ---
    credits_value = None
    if wallet:
        credits_map = load_ai_credits()
        try:
            credits_value = int(credits_map.get(wallet, 0) or 0)
        except (TypeError, ValueError):
            credits_value = 0

        if credits_value <= 0:
            warning_text = (
                "Δεν έχεις άλλα Quantum credits γι' αυτό το THR wallet.\\n"
                "Πήγαινε στη σελίδα AI Packs και αγόρασε πακέτο για να συνεχίσεις."
            )
            return jsonify(
                response=warning_text,
                quantum_key=ai_agent.generate_quantum_key(),
                status="no_credits",
                wallet=wallet,
                credits=0,
                files=[],
                session_id=session_id,
            ), 200

    # --- Κλήση στον ThronosAI provider ---
    # Pass model_key AND session_id to generate_response
    raw = ai_agent.generate_response(msg, wallet=wallet, model_key=model_key, session_id=session_id)

    if isinstance(raw, dict):
        full_text = str(raw.get("response") or "")
        quantum_key = raw.get("quantum_key") or ai_agent.generate_quantum_key()
        status = raw.get("status", "secure")
        provider = raw.get("provider", "unknown")
        model = raw.get("model", "unknown")
    else:
        full_text = str(raw)
        quantum_key = ai_agent.generate_quantum_key()
        status = "secure"
        provider = "unknown"
        model = "unknown"

    # --- FILE blocks -> αρχεία ---
    try:
        files, cleaned = extract_ai_files_from_text(full_text)
    except Exception as e:
        print("AI file extraction error:", e)
        files = []
        cleaned = full_text

    # --- Offline corpus + sessions ---
    try:
        enqueue_offline_corpus(wallet, msg, full_text, files, session_id=session_id)
    except Exception as e:
        print("offline corpus enqueue error:", e)

    # --- Credit burn ---
    if wallet:
        credits_map = load_ai_credits()
        try:
            before = int(credits_map.get(wallet, 0) or 0)
        except (TypeError, ValueError):
            before = 0
        after = max(0, before - AI_CREDIT_COST_PER_MSG)
        credits_map[wallet] = after
        save_ai_credits(credits_map)
        credits_for_frontend = after
    else:
        credits_for_frontend = "infinite"

    resp = {
        "response": cleaned,
        "quantum_key": quantum_key,
        "status": status,
        "provider": provider,
        "model": model,
        "wallet": wallet,
        "files": files,
        "credits": credits_for_frontend,
        "session_id": session_id,
    }
    return jsonify(resp), 200

@app.route("/api/upload_training_data", methods=["POST"])
def api_upload_training_data():
    """
    Επιτρέπει το upload αρχείων για 'εκπαίδευση' ή εμπλουτισμό του corpus.
    """
    if "file" not in request.files:
        return jsonify(error="No file part"), 400
    file = request.files["file"]
    wallet = request.form.get("wallet", "").strip()

    if file.filename == "":
        return jsonify(error="No selected file"), 400

    try:
        filename = secure_filename(file.filename)
        # Προσθήκη timestamp για μοναδικότητα
        safe_name = f"{int(time.time())}_{filename}"
        file_path = os.path.join(AI_FILES_DIR, safe_name)
        
        file.save(file_path)
        
        # Καταγραφή στο offline corpus
        # Φτιάχνουμε μια δομή που να ταιριάζει με το enqueue_offline_corpus
        file_obj = {"filename": safe_name}
        enqueue_offline_corpus(wallet, "[System] Upload Training Data", f"File uploaded: {safe_name}", [file_obj])

        print(f"📂 AI Training Data Uploaded: {safe_name} by {wallet}")
        return jsonify(status="success", filename=safe_name, message="File uploaded to AI corpus"), 200

    except Exception as e:
        print("Upload Error:", e)
        return jsonify(error=str(e)), 500


@app.route("/api/ai_upload", methods=["POST"])
def api_ai_upload():
    if "file" not in request.files:
        return jsonify(error="No file part"), 400
    file = request.files["file"]
    wallet = request.form.get("wallet", "").strip()
    session_id = (request.form.get("session_id") or "").strip() or None

    if file.filename == "":
        return jsonify(error="No selected file"), 400

    try:
        filename = secure_filename(file.filename)
        safe_name = f"{int(time.time())}_{filename}"
        file_path = os.path.join(AI_FILES_DIR, safe_name)
        file.save(file_path)

        file_obj = {"filename": safe_name}
        enqueue_offline_corpus(
            wallet,
            "[System] Upload Training Data",
            f"File uploaded: {safe_name}",
            [file_obj],
            session_id=session_id,
        )

        print(f"📂 AI Training Data Uploaded: {safe_name} by {wallet}")
        return jsonify(status="success", filename=safe_name, message="File uploaded to AI corpus"), 200

    except Exception as e:
        print("Upload Error:", e)
        return jsonify(error=str(e)), 500


# ─── AI PACKS API ──────────────────────────────────────────────────────────────

@app.route("/api/ai_credits", methods=["GET"])
def api_ai_credits():
    """
    Επιστρέφει τα διαθέσιμα AI credits για ένα wallet.
    Αν δεν δοθεί wallet, θεωρούμε demo / infinite.
    """
    wallet = (request.args.get("wallet") or "").strip()
    if not wallet:
        return jsonify({"credits": "infinite"}), 200

    credits_map = load_ai_credits()
    try:
        value = int(credits_map.get(wallet, 0) or 0)
    except (TypeError, ValueError):
        value = 0
    return jsonify({"wallet": wallet, "credits": value}), 200


@app.route("/api/ai_history", methods=["GET"])
def api_ai_history():
    """
    Ιστορικό AI συνομιλιών για συγκεκριμένο THR wallet.
    Βασίζεται στο ai_offline_corpus.json.
    """
    wallet = (request.args.get("wallet") or "").strip()
    corpus = load_json(AI_CORPUS_FILE, [])

    history = []
    for entry in corpus:
        if wallet and entry.get("wallet") != wallet:
            continue
        ts = entry.get("timestamp", "")
        prompt = entry.get("prompt", "")
        response = entry.get("response", "")

        if prompt:
            history.append({"role": "user", "content": prompt, "ts": ts})
        if response:
            history.append({"role": "assistant", "content": response, "ts": ts})

    history = history[-40:]  # τα τελευταία 40 μηνύματα για να μην φορτώνει άπειρα
    return jsonify({"wallet": wallet, "history": history}), 200

@app.route("/api/ai_sessions", methods=["GET"])
def api_ai_sessions():
    """
    Επιστρέφει όλες τις AI sessions για συγκεκριμένο wallet.
    """
    wallet = (request.args.get("wallet") or "").strip()
    sessions = load_ai_sessions()
    if wallet:
        sessions = [s for s in sessions if s.get("wallet") == wallet]

    # ταξινόμηση με βάση updated_at (πιο πρόσφατη πρώτη)
    def _key(s):
        return s.get("updated_at", "")
    sessions.sort(key=_key, reverse=True)

    return jsonify({"wallet": wallet, "sessions": sessions}), 200

@app.route("/api/ai_sessions/start", methods=["POST"])
def api_ai_session_start():
    """
    Δημιουργεί νέα session για ένα wallet.
    """
    data = request.get_json() or {}
    wallet = (data.get("wallet") or "").strip()
    title = (data.get("title") or "").strip()

    if not wallet:
        return jsonify(error="Wallet required"), 400

    sid = secrets.token_hex(8)
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    if not title:
        title = "Νέα συνομιλία"

    sessions = load_ai_sessions()
    session = {
        "id": sid,
        "wallet": wallet,
        "title": title[:80],
        "created_at": ts,
        "updated_at": ts,
    }
    sessions.append(session)
    save_ai_sessions(sessions)

    return jsonify(status="ok", session=session), 200

@app.route("/api/ai_sessions/rename", methods=["POST"])
def api_ai_session_rename():
    """
    Μετονομάζει μια session.
    """
    data = request.get_json() or {}
    wallet = (data.get("wallet") or "").strip()
    session_id = (data.get("session_id") or "").strip()
    new_title = (data.get("title") or "").strip()

    if not wallet or not session_id or not new_title:
        return jsonify(error="Missing parameters"), 400

    sessions = load_ai_sessions()
    found = False
    for s in sessions:
        if s.get("wallet") == wallet and s.get("id") == session_id:
            s["title"] = new_title[:80]
            found = True
            break
    
    if found:
        save_ai_sessions(sessions)
        return jsonify(status="ok", title=new_title), 200
    else:
        return jsonify(error="Session not found"), 404

@app.route("/api/ai_session_history", methods=["GET"])
def api_ai_session_history():
    """
    Ιστορικό για συγκεκριμένη session (wallet + session_id).
    """
    wallet = (request.args.get("wallet") or "").strip()
    session_id = (request.args.get("session_id") or "").strip() or "default"

    corpus = load_json(AI_CORPUS_FILE, [])
    history = []

    for entry in corpus:
        if wallet and entry.get("wallet") != wallet:
            continue
        if (entry.get("session_id") or "default") != session_id:
            continue

        ts = entry.get("timestamp", "")
        prompt = entry.get("prompt", "")
        response = entry.get("response", "")

        if prompt:
            history.append({"role": "user", "content": prompt, "ts": ts})
        if response:
            history.append({"role": "assistant", "content": response, "ts": ts})

    history = history[-80:]
    return jsonify({"wallet": wallet, "session_id": session_id, "history": history}), 200


@app.route("/api/ai_packs", methods=["GET"])
def api_ai_packs():
    """
    Επιστρέφει τη λίστα των διαθέσιμων AI packs.
    Αν υπάρχει ai_packs.json στο DATA_DIR, το διαβάζει από εκεί,
    αλλιώς χρησιμοποιεί τα AI_DEFAULT_PACKS.
    """
    packs = load_ai_packs()
    return jsonify({"packs": packs}), 200


@app.route("/api/ai_purchase_pack", methods=["POST"])
def api_ai_purchase_pack():
    """
    Πληρωμή AI pack με THR:

    - Παίρνει { wallet, pack } από JSON
    - Ελέγχει υπόλοιπο στο ledger
    - Χρεώνει τον χρήστη, πιστώνει το AI_WALLET_ADDRESS
    - Γράφει service_payment TX στο CHAIN_FILE
    - Αυξάνει τα credits του wallet στο ai_credits.json
    """
    data = request.get_json() or {}
    wallet = (data.get("wallet") or "").strip()
    code   = (data.get("pack") or "").strip()

    if not wallet or not code:
        return jsonify(
            status="denied",
            message="Wallet και pack code είναι υποχρεωτικά."
        ), 400

    packs = load_ai_packs()
    pack = next((p for p in packs if p.get("code") == code), None)
    if not pack:
        return jsonify(status="denied", message="Άγνωστο AI pack."), 400

    try:
        price = float(pack.get("price_thr", 0.0))
    except Exception:
        price = 0.0

    if price <= 0:
        return jsonify(status="denied", message="Μη έγκυρη τιμή πακέτου."), 400

    # --- Ledger έλεγχος & μεταφορά THR ---
    ledger = load_json(LEDGER_FILE, {})
    balance = float(ledger.get(wallet, 0.0))

    if balance < price:
        return jsonify(
            status="denied",
            message=f"Insufficient THR funds (έχεις {balance}, χρειάζονται {price})."
        ), 400

    ledger[wallet] = round(balance - price, 6)
    ledger[AI_WALLET_ADDRESS] = round(
        float(ledger.get(AI_WALLET_ADDRESS, 0.0)) + price,
        6,
    )
    save_json(LEDGER_FILE, ledger)

    # --- Credits ledger ---
    credits = load_ai_credits()
    current_credits = int(credits.get(wallet, 0))
    add_credits = int(pack.get("credits", 0))
    total_credits = current_credits + add_credits
    credits[wallet] = total_credits
    save_ai_credits(credits)

    # --- Chain TX (service_payment) ---
    chain = load_json(CHAIN_FILE, [])
    tx = {
        "type": "service_payment",
        "service": "AI_PACK",
        "pack_code": pack.get("code"),
        "pack_credits": add_credits,
        "from": wallet,
        "to": AI_WALLET_ADDRESS,
        "amount": price,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": f"AI-{int(time.time())}-{len(chain)}",
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)

    print(
        f"🤖 AI Pack purchased: {pack.get('code')} by {wallet} "
        f"({add_credits} credits, total={total_credits})"
    )

    return jsonify(
        status="granted",
        pack=pack,
        total_credits=total_credits,
    ), 200


# ─── CRYPTO HUNTERS GAME API ───────────────────────
@app.route("/api/game/submit_score", methods=["POST"])
def api_game_submit_score():
    """
    Handles score submission from the Crypto Hunters game.
    Distributes THR rewards from AI Treasury or Mints new tokens.
    """
    try:
        data = request.get_json() or {}
        wallet = (data.get("wallet") or "").strip()
        score = int(data.get("score", 0))
        reward_claim = float(data.get("reward", 0.0))

        if not wallet or score <= 0 or reward_claim <= 0:
            return jsonify(status="error", message="Invalid game data"), 400

        # Simple validation: Reward should be approx score * 0.001
        expected_reward = score * 0.001
        if abs(reward_claim - expected_reward) > 0.0001:
             return jsonify(status="error", message="Reward mismatch"), 400

        # Limit max reward per claim to prevent abuse (e.g., 10 THR max)
        if reward_claim > 10.0:
            return jsonify(status="error", message="Reward exceeds limit"), 400

        ledger = load_json(LEDGER_FILE, {})
        chain = load_json(CHAIN_FILE, [])
        
        # Check AI Treasury Balance
        ai_balance = float(ledger.get(AI_WALLET_ADDRESS, 0.0))
        
        tx_type = "game_reward"
        sender = AI_WALLET_ADDRESS
        
        if ai_balance >= reward_claim:
            # Pay from Treasury
            ledger[AI_WALLET_ADDRESS] = round(ai_balance - reward_claim, 6)
        else:
            # Treasury empty, Mint new tokens (Inflationary fallback)
            sender = "COINBASE_GAME"
            # No debit from AI wallet
            
        # Credit User
        user_balance = float(ledger.get(wallet, 0.0))
        ledger[wallet] = round(user_balance + reward_claim, 6)
        
        save_json(LEDGER_FILE, ledger)
        
        # Record Transaction
        tx = {
            "type": tx_type,
            "from": sender,
            "to": wallet,
            "amount": reward_claim,
            "score": score,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "tx_id": f"GAME-{int(time.time())}-{secrets.token_hex(4)}",
            "status": "confirmed"
        }
        chain.append(tx)
        save_json(CHAIN_FILE, chain)
        update_last_block(tx, is_block=False)
        
        print(f"🎮 Game Reward: {reward_claim} THR to {wallet} (Score: {score})")
        
        return jsonify(status="success", tx_id=tx["tx_id"], new_balance=ledger[wallet]), 200

    except Exception as e:
        logger.error(f"Game Submit Error: {e}")
        return jsonify(status="error", message=str(e)), 500


# ─── NODE REGISTRATION / IOT KIT ───────────────────
@app.route("/register_node", methods=["POST"])
def register_node():
    address = request.form.get("address","").strip()
    secret  = request.form.get("secret","").strip()
    if not address or not secret:
        return "Address and Secret are required",400
    node_id=str(uuid.uuid4())
    config={
        "node_id":node_id,
        "wallet_address":address,
        "secret":secret,
        "server_url":"https://thrchain.up.railway.app"
    }
    config_json=json.dumps(config,indent=4)
    start_script=f"""
import os, sys, subprocess
print("Starting Thronos IoT Vehicle Node...")
print("Node ID: {node_id}")
print("Wallet: {address}")
try:
    import PIL, requests, cryptography  # noqa
except Exception:
    print("Installing dependencies (pillow, requests, cryptography)...")
    subprocess.check_call([sys.executable,"-m","pip","install","requests","pillow","cryptography"])
try:
    subprocess.run([sys.executable,"iot_vehicle_node.py"], check=True)
except KeyboardInterrupt:
    print("\\nNode stopped.")
except Exception as e:
    print(f"Error: {{e}}"); input("Press Enter to exit...")
"""
    try:
        with open(os.path.join(BASE_DIR,"iot_vehicle_node.py"),"r",encoding="utf-8") as f:
            node_script=f.read()
    except FileNotFoundError:
        node_script="# iot_vehicle_node.py not found on server."
    memory_file=io.BytesIO()
    with zipfile.ZipFile(memory_file,"w",zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("node_config.json",config_json)
        zf.writestr("start_iot.py",start_script)
        zf.writestr("iot_vehicle_node.py",node_script)
        pic_path=os.path.join(BASE_DIR,"images/Vehicle.jpg") # FIX: Remove leading slash
        if os.path.exists(pic_path):
            zf.write(pic_path,"images/Vehicle.jpg")
        else:
            zf.writestr("images/Vehicle.jpg","")
        zf.writestr("README.txt","1. Install Python 3.\\n2. Run 'python start_iot.py' (auto-installs deps).")
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"iot_node_kit_{node_id[:8]}.zip"
    )


# ─── PLEDGE FLOW ───────────────────────────────────
@app.route("/pledge")
def pledge_form():
    return render_template("pledge_form.html")

@app.route("/pledge_submit", methods=["POST"])
def pledge_submit():
    data = request.get_json() or {}
    btc_address=(data.get("btc_address") or "").strip()
    pledge_text=(data.get("pledge_text") or "").strip()
    passphrase=(data.get("passphrase") or "").strip()
    if not btc_address:
        return jsonify(error="Missing BTC address"),400
    pledges = load_json(PLEDGE_CHAIN, [])
    exists = next((p for p in pledges if p["btc_address"]==btc_address), None)
    if exists:
        return jsonify(
            status="already_verified",
            thr_address=exists["thr_address"],
            pledge_hash=exists["pledge_hash"],
            pdf_filename=exists.get("pdf_filename",f"pledge_{exists['thr_address']}.pdf")
        ),200
    free_list=load_json(WHITELIST_FILE,[])
    paid, txns = (True,[]) if btc_address in free_list else verify_btc_payment(btc_address)
    if not paid:
        return jsonify(status="pending",message="Waiting for BTC payment",txns=txns),200
    thr_addr=f"THR{int(time.time()*1000)}"
    phash = hashlib.sha256((btc_address+pledge_text).encode()).hexdigest()
    send_seed=secrets.token_hex(16)
    send_seed_hash=hashlib.sha256(send_seed.encode()).hexdigest()
    auth_string=f"{send_seed}:{passphrase}:auth" if passphrase else f"{send_seed}:auth"
    send_auth_hash=hashlib.sha256(auth_string.encode()).hexdigest()
    pledge_entry={
        "btc_address":btc_address,
        "pledge_text":pledge_text,
        "timestamp":time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "pledge_hash":phash,
        "thr_address":thr_addr,
        "send_seed_hash":send_seed_hash,
        "send_auth_hash":send_auth_hash,
        "has_passphrase":bool(passphrase)
    }
    chain=load_json(CHAIN_FILE,[])
    height=len(chain)
    pdf_name=create_secure_pdf_contract(
        btc_address, pledge_text, thr_addr, phash, height, send_seed, CONTRACTS_DIR, passphrase
    )
    pledge_entry["pdf_filename"]=pdf_name
    pledges.append(pledge_entry)
    save_json(PLEDGE_CHAIN, pledges)
    return jsonify(
        status="verified",
        thr_address=thr_addr,
        pledge_hash=phash,
        pdf_filename=pdf_name,
        send_secret=send_seed
    ),200


@app.route("/wallet_data/<thr_addr>")
def wallet_data(thr_addr):
    ledger=load_json(LEDGER_FILE,{})
    wbtc_ledger=load_json(WBTC_LEDGER_FILE,{}) # NEW
    
    chain=load_json(CHAIN_FILE,[])
    bal=round(float(ledger.get(thr_addr,0.0)),6)
    wbtc_bal=round(float(wbtc_ledger.get(thr_addr,0.0)),8) # NEW
    
    history=[
        tx for tx in chain
        if isinstance(tx,dict) and (tx.get("from")==thr_addr or tx.get("to")==thr_addr)
    ]
    return jsonify(balance=bal, wbtc_balance=wbtc_bal, transactions=history),200

@app.route("/wallet/<thr_addr>")
def wallet_redirect(thr_addr):
    return redirect(url_for("wallet_data", thr_addr=thr_addr)),302


@app.route("/send_thr", methods=["POST"])
def send_thr():
    data = request.get_json() or {}
    from_thr=(data.get("from_thr") or "").strip()
    to_thr=(data.get("to_thr") or "").strip()
    amount_raw=data.get("amount",0)
    auth_secret=(data.get("auth_secret") or "").strip()
    passphrase=(data.get("passphrase") or "").strip()
    try:
        amount=float(amount_raw)
    except (TypeError,ValueError):
        return jsonify(error="invalid_amount"),400
    if not from_thr or not to_thr:
        return jsonify(error="missing_from_or_to"),400
    if amount<=0:
        return jsonify(error="amount_must_be_positive"),400
    if not auth_secret:
        return jsonify(error="missing_auth_secret"),400
    pledges=load_json(PLEDGE_CHAIN,[])
    sender_pledge=next((p for p in pledges if p.get("thr_address")==from_thr),None)
    if not sender_pledge:
        return jsonify(error="unknown_sender_thr"),404
    stored_auth_hash=sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(error="send_not_enabled_for_this_thr"),400
    if sender_pledge.get("has_passphrase"):
        if not passphrase:
            return jsonify(error="passphrase_required"),400
        auth_string=f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string=f"{auth_secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest()!=stored_auth_hash:
        return jsonify(error="invalid_auth"),403

    # --- Dynamic Fee Calculation ---
    fee = calculate_dynamic_fee(amount)
    total_cost = amount + fee

    ledger=load_json(LEDGER_FILE,{})
    sender_balance=float(ledger.get(from_thr,0.0))
    
    if sender_balance<total_cost:
        return jsonify(
            error="insufficient_balance",
            balance=round(sender_balance,6),
            required=total_cost,
            fee=fee
        ),400
    ledger[from_thr]=round(sender_balance-total_cost,6)
    save_json(LEDGER_FILE,ledger)
    chain=load_json(CHAIN_FILE,[])
    tx={
        "type":"transfer",
        "height":None,
        "timestamp":time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "from":from_thr,
        "to":to_thr,
        "amount":round(amount,6),
        "fee_burned":fee,
        "tx_id":f"TX-{len(chain)}-{int(time.time())}",
        "thr_address":from_thr,
        "status":"pending",
        "confirmation_policy": "FAST",
        "min_signers": 1,
    }
    pool=load_mempool()
    pool.append(tx)
    save_mempool(pool)
    update_last_block(tx,is_block=False)
    return jsonify(status="pending", tx=tx, new_balance_from=ledger[from_thr], fee_burned=fee),200

# ─── SWAP API ──────────────────────────────────────
@app.route("/api/swap", methods=["POST"])
def api_swap():
    data = request.get_json() or {}
    wallet = data.get("wallet")
    secret = data.get("secret")
    
    try:
        amount = float(data.get("amount", 0))
    except (ValueError, TypeError):
        return jsonify(status="error", message="Invalid amount"), 400
        
    direction = data.get("direction") # THR_TO_BTC or BTC_TO_THR
    
    if not wallet or not secret or amount <= 0:
        return jsonify(status="error", message="Invalid input"), 400

    # Verify Auth (Reusing logic from send_thr)
    pledges=load_json(PLEDGE_CHAIN,[])
    sender_pledge=next((p for p in pledges if p.get("thr_address")==wallet),None)
    if not sender_pledge:
        return jsonify(status="error", message="Unknown wallet"), 404
    
    stored_auth_hash=sender_pledge.get("send_auth_hash")
    
    # Try both auth methods (with and without passphrase) if possible, 
    # but here we only have 'secret'. 
    # If user has passphrase, this simple swap UI might fail. 
    # For now, we assume standard auth.
    auth_string=f"{secret}:auth" 
    
    if hashlib.sha256(auth_string.encode()).hexdigest()!=stored_auth_hash:
        return jsonify(status="error", message="Invalid secret (or passphrase required)"), 403

    ledger = load_json(LEDGER_FILE, {})
    wbtc_ledger = load_json(WBTC_LEDGER_FILE, {})
    chain = load_json(CHAIN_FILE, [])
    
    RATE = 0.0001 # 1 THR = 0.0001 BTC
    
    tx_id = f"SWAP-{int(time.time())}-{secrets.token_hex(4)}"
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    if direction == "THR_TO_BTC":
        # Burn THR, Mint wBTC
        thr_bal = float(ledger.get(wallet, 0.0))
        if thr_bal < amount:
            return jsonify(status="error", message="Insufficient THR"), 400
            
        btc_out = amount * RATE
        
        ledger[wallet] = round(thr_bal - amount, 6)
        wbtc_ledger[wallet] = round(float(wbtc_ledger.get(wallet, 0.0)) + btc_out, 8)
        
        # Log TX
        tx = {
            "type": "swap",
            "from": wallet,
            "to": SWAP_POOL_ADDRESS,
            "amount_in": amount,
            "token_in": "THR",
            "amount_out": btc_out,
            "token_out": "wBTC",
            "tx_id": tx_id,
            "timestamp": ts,
            "status": "confirmed" # Instant swap
        }
        
    elif direction == "BTC_TO_THR":
        # Burn wBTC, Mint THR
        wbtc_bal = float(wbtc_ledger.get(wallet, 0.0))
        if wbtc_bal < amount:
            return jsonify(status="error", message="Insufficient wBTC"), 400
            
        thr_out = amount / RATE
        
        wbtc_ledger[wallet] = round(wbtc_bal - amount, 8)
        ledger[wallet] = round(float(ledger.get(wallet, 0.0)) + thr_out, 6)
        
        tx = {
            "type": "swap",
            "from": wallet,
            "to": SWAP_POOL_ADDRESS,
            "amount_in": amount,
            "token_in": "wBTC",
            "amount_out": thr_out,
            "token_out": "THR",
            "tx_id": tx_id,
            "timestamp": ts,
            "status": "confirmed"
        }
    else:
        return jsonify(status="error", message="Invalid direction"), 400

    save_json(LEDGER_FILE, ledger)
    save_json(WBTC_LEDGER_FILE, wbtc_ledger)
    
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    
    return jsonify(status="success", tx_id=tx_id), 200

# ─── GATEWAY API ───────────────────────────────────
@app.route("/api/gateway/buy", methods=["POST"])
def api_gateway_buy():
    data = request.get_json() or {}
    wallet = data.get("wallet")
    try:
        fiat_amount = float(data.get("fiat_amount", 0))
    except (ValueError, TypeError):
        return jsonify(status="error", message="Invalid amount"), 400
        
    currency = data.get("currency", "USD")
    
    if not wallet or fiat_amount <= 0:
        return jsonify(status="error", message="Invalid input"), 400
    
    # Rate: 1 THR = $10 (Simulated)
    rate = 10.0
    thr_amount = fiat_amount / rate
    
    ledger = load_json(LEDGER_FILE, {})
    chain = load_json(CHAIN_FILE, [])
    
    # Credit user (Minting logic for simulation)
    ledger[wallet] = round(float(ledger.get(wallet, 0.0)) + thr_amount, 6)
    save_json(LEDGER_FILE, ledger)
    
    tx = {
        "type": "fiat_buy",
        "from": "FIAT_GATEWAY",
        "to": wallet,
        "amount": thr_amount,
        "fiat_amount": fiat_amount,
        "currency": currency,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": f"BUY-{int(time.time())}-{secrets.token_hex(4)}",
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    
    return jsonify(status="success", tx_id=tx["tx_id"], thr_amount=thr_amount), 200

@app.route("/api/gateway/sell", methods=["POST"])
def api_gateway_sell():
    data = request.get_json() or {}
    wallet = data.get("wallet")
    secret = data.get("secret")
    try:
        thr_amount = float(data.get("thr_amount", 0))
    except (ValueError, TypeError):
        return jsonify(status="error", message="Invalid amount"), 400
        
    currency = data.get("currency", "USD")
    
    if not wallet or not secret or thr_amount <= 0:
        return jsonify(status="error", message="Invalid input"), 400

    # Verify Auth
    pledges=load_json(PLEDGE_CHAIN,[])
    sender_pledge=next((p for p in pledges if p.get("thr_address")==wallet),None)
    if not sender_pledge:
        return jsonify(status="error", message="Unknown wallet"), 404
    
    stored_auth_hash=sender_pledge.get("send_auth_hash")
    auth_string=f"{secret}:auth"
    if hashlib.sha256(auth_string.encode()).hexdigest()!=stored_auth_hash:
        return jsonify(status="error", message="Invalid secret"), 403
        
    ledger = load_json(LEDGER_FILE, {})
    balance = float(ledger.get(wallet, 0.0))
    
    if balance < thr_amount:
        return jsonify(status="error", message="Insufficient THR"), 400
        
    # Rate: 1 THR = $10
    rate = 10.0
    fiat_out = thr_amount * rate
    
    # Deduct THR
    ledger[wallet] = round(balance - thr_amount, 6)
    save_json(LEDGER_FILE, ledger)
    
    chain = load_json(CHAIN_FILE, [])
    tx = {
        "type": "fiat_sell",
        "from": wallet,
        "to": "FIAT_GATEWAY",
        "amount": thr_amount,
        "fiat_amount": fiat_out,
        "currency": currency,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": f"SELL-{int(time.time())}-{secrets.token_hex(4)}",
        "status": "confirmed"
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    update_last_block(tx, is_block=False)
    
    return jsonify(status="success", tx_id=tx["tx_id"], fiat_amount=fiat_out), 200


# ─── ADMIN WHITELIST + MIGRATION ───────────────────
@app.route("/admin/whitelist", methods=["GET"])
def admin_whitelist_page():
    secret=request.args.get("secret","")
    if secret!=ADMIN_SECRET:
        return "Forbidden (wrong or missing secret)",403
    return render_template("admin_whitelist.html", admin_secret=secret)

@app.route("/admin/whitelist/add", methods=["POST"])
def admin_whitelist_add():
    data=request.get_json() or {}
    if data.get("secret")!=ADMIN_SECRET:
        return jsonify(error="forbidden"),403
    btc=(data.get("btc_address") or "").strip()
    if not btc:
        return jsonify(error="missing_btc_address"),400
    wl=load_json(WHITELIST_FILE,[])
    if btc not in wl:
        wl.append(btc)
        save_json(WHITELIST_FILE, wl)
    return jsonify(status="ok",whitelist=wl),200

@app.route("/admin/whitelist/list", methods=["GET"])
def admin_whitelist_list():
    secret=request.args.get("secret","")
    if secret!=ADMIN_SECRET:
        return jsonify(error="forbidden"),403
    return jsonify(whitelist=load_json(WHITELIST_FILE,[])),200

@app.route("/admin/migrate_seeds", methods=["POST","GET"])
def admin_migrate_seeds():
    payload=request.get_json() or {}
    secret=request.args.get("secret","") or payload.get("secret","")
    if secret!=ADMIN_SECRET:
        return jsonify(error="forbidden"),403
    pledges=load_json(PLEDGE_CHAIN,[])
    changed=[]
    for p in pledges:
        if p.get("send_seed_hash") and p.get("send_auth_hash"):
            continue
        thr_addr=p["thr_address"]
        btc_address=p["btc_address"]
        pledge_text=p["pledge_text"]
        pledge_hash=p["pledge_hash"]
        send_seed=secrets.token_hex(16)
        send_seed_hash=hashlib.sha256(send_seed.encode()).hexdigest()
        send_auth_hash=hashlib.sha256(f"{send_seed}:auth".encode()).hexdigest()
        p["send_seed_hash"]=send_seed_hash
        p["send_auth_hash"]=send_auth_hash
        p["has_passphrase"]=False
        chain=load_json(CHAIN_FILE,[])
        height=len(chain)
        pdf_name=create_secure_pdf_contract(
            btc_address, pledge_text, thr_addr, pledge_hash, height, send_seed, CONTRACTS_DIR
        )
        p["pdf_filename"]=pdf_name
        changed.append({
            "thr_address":thr_addr,
            "btc_address":btc_address,
            "send_seed":send_seed,
            "pdf_filename":pdf_name
        })
    save_json(PLEDGE_CHAIN, pledges)
    return jsonify(migrated=changed),200


# ─── QUORUM LAYER – aggregation API surface (BLS placeholder) ───────────────
def _tx_message_bytes(tx: dict) -> bytes:
    material = f"{tx.get('from','')}|{tx.get('to','')}|{tx.get('amount',0)}|{tx.get('tx_id','')}"
    return hashlib.sha256(material.encode()).digest()

@app.route("/api/attest", methods=["POST"])
def api_attest():
    data=request.get_json() or {}
    tx_id=(data.get("tx_id") or "").strip()
    signer=(data.get("signer") or "").strip()
    partial_sig=(data.get("partial_sig") or "").strip()
    pubkey=(data.get("pubkey") or "").strip()
    scheme=(data.get("scheme") or "BLS").upper()
    if not (tx_id and signer and partial_sig and pubkey):
        return jsonify(error="missing_fields"),400
    pool=load_mempool()
    tx=next((t for t in pool if t.get("tx_id")==tx_id),None)
    if not tx:
        chain=load_json(CHAIN_FILE,[])
        tx=next((t for t in chain if t.get("tx_id")==tx_id and t.get("status")!="confirmed"),None)
    if not tx:
        return jsonify(error="unknown_tx"),404
    store=load_attest_store()
    bucket=store.get(tx_id, {"scheme":scheme, "items":[]})
    already={ (i.get("pubkey"), i.get("signer")) for i in bucket["items"] }
    if (pubkey, signer) not in already:
        bucket["items"].append({"signer":signer,"sig":partial_sig,"pubkey":pubkey,"ts":int(time.time())})
        store[tx_id]=bucket
        save_attest_store(store)
    if "signers" not in tx:
        tx["signers"]=[]
    if tx.get("status") not in ("pending","confirmed"):
        tx["status"]="quoruming"
    save_mempool([t if t.get("tx_id")!=tx_id else tx for t in pool])
    return jsonify(status="accepted", collected=len(bucket["items"]), scheme=bucket["scheme"]),200

@app.route("/api/tx/<tx_id>/verify", methods=["GET"])
def api_verify_tx_sig(tx_id):
    pool=load_mempool()
    tx=next((t for t in pool if t.get("tx_id")==tx_id),None)
    if not tx:
        return jsonify(error="unknown_tx"),404
    msg=_tx_message_bytes(tx)
    ok=False
    if tx.get("aggregate_sig") and tx.get("pubkeys"):
        ok=qc_verify(tx["aggregate_sig"], tx["pubkeys"], msg, tx.get("att_scheme","BLS"))
    return jsonify(tx_id=tx_id, verified=bool(ok)),200

def aggregator_step():
    pool=load_mempool()
    if not pool:
        return
    store=load_attest_store()
    changed=False
    for tx in pool:
        if tx.get("status")=="confirmed":
            continue
        policy=(tx.get("confirmation_policy") or "FAST").upper()
        min_signers=int(tx.get("min_signers") or 1)
        bucket=store.get(tx["tx_id"], {"items":[], "scheme":"BLS"})
        items=bucket.get("items",[])
        normalized=[]
        for it in items:
            if not it.get("sig"):
                it["sig"]=it.get("partial_sig")
            if it.get("pubkey") and it.get("sig"):
                normalized.append({
                    "pubkey":it["pubkey"],
                    "sig":it["sig"],
                    "signer":it.get("signer", it.get("pubkey")[:12])
                })
        if not normalized:
            if policy=="FAST":
                if tx.get("status")!="pending":
                    tx["status"]="pending"; changed=True
            else:
                if tx.get("status")!="quoruming":
                    tx["status"]="quoruming"; changed=True
            continue
        if len(normalized) >= min_signers:
            msg=_tx_message_bytes(tx)
            res=qc_aggregate(normalized, bucket.get("scheme","BLS"), msg)
            if res:
                tx["aggregate_sig"]=res.get("agg_sig")
                tx["signers"]=res.get("signers",[])
                tx["pubkeys"]=res.get("pubkeys",[])
                tx["att_scheme"]=res.get("scheme")
                if tx.get("status")!="pending":
                    tx["status"]="pending"
                changed=True
        else:
            if policy=="FAST":
                if tx.get("status")!="pending":
                    tx["status"]="pending"; changed=True
            else:
                if tx.get("status")!="quoruming":
                    tx["status"]="quoruming"; changed=True
    if changed:
        save_mempool(pool)


# ─── MINING ENDPOINT ───────────────────────────────
@app.route("/submit_block", methods=["POST"])
def submit_block():
    data = request.get_json() or {}
    thr_address = data.get("thr_address")
    nonce = data.get("nonce")
    if not thr_address or nonce is None:
        return jsonify(error="Missing mining data"),400
    chain=load_json(CHAIN_FILE,[])
    
    server_last_hash = ""
    blocks=[b for b in chain if isinstance(b,dict) and b.get("reward") is not None]
    if blocks:
        server_last_hash = blocks[-1].get("block_hash","")
    else:
        server_last_hash = "0"*64
        
    is_stratum = "merkle_root" in data
    pow_hash=""
    prev_hash=""
    if is_stratum:
        merkle_root=data.get("merkle_root")
        prev_hash=data.get("prev_hash")
        time_val=data.get("time")
        nbits=data.get("nbits")
        version=data.get("version",1)
        if not all([merkle_root, prev_hash, time_val, nbits]):
            return jsonify(error="Missing Stratum fields"),400
        if prev_hash!=server_last_hash:
            return jsonify(error="Stale block (prev_hash mismatch)"),400
        try:
            header  = struct.pack("<I",version)
            header += bytes.fromhex(prev_hash)[::-1]
            header += bytes.fromhex(merkle_root)[::-1]
            header += struct.pack("<I",time_val)
            header += struct.pack("<I",nbits)
            header += struct.pack("<I",nonce)
            pow_hash = sha256d(header)[::-1].hex()
        except Exception as e:
            return jsonify(error=f"Header construction failed: {e}"),400
    else:
        pow_hash=data.get("pow_hash")
        prev_hash=data.get("prev_hash")
        if prev_hash!=server_last_hash:
            return jsonify(error="Stale block (prev_hash mismatch)"),400
        check=hashlib.sha256((prev_hash+thr_address).encode()+str(nonce).encode()).hexdigest()
        if check!=pow_hash:
            return jsonify(error="Invalid hash calculation"),400
            
    current_target = get_mining_target()
    if int(pow_hash, 16) > current_target:
        return jsonify(error=f"Insufficient difficulty. Target: {hex(current_target)}"), 400

    # Reward split με σωστό height (blocks + offset)
    local_height  = len(blocks)
    height        = HEIGHT_OFFSET + local_height
    total_reward  = calculate_reward(height)
    
    miner_share=round(total_reward*0.80,6)
    ai_share=round(total_reward*0.10,6)
    burn_share=round(total_reward*0.10,6)
    ts=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    new_block={
        "thr_address":thr_address,
        "timestamp":ts,
        "block_hash":pow_hash,
        "prev_hash":prev_hash,
        "nonce":nonce,
        "reward":total_reward,
        "reward_split":{"miner":miner_share,"ai":ai_share,"burn":burn_share},
        "pool_fee":burn_share,
        "reward_to_miner":miner_share,
        "height":height,
        "type":"block",
        "target":current_target,
        "is_stratum":is_stratum
    }
    chain.append(new_block)

    # include mempool TXs
    pool=load_mempool()
    included=[]
    if pool:
        for tx in list(pool):
            tx["height"]=height
            tx["status"]="confirmed"
            tx["timestamp"]=ts
            chain.append(tx)
            included.append(tx)
        save_mempool([])

        ledger=load_json(LEDGER_FILE,{})
        for tx in included:
            if tx.get("type")=="transfer":
                to_thr=tx["to"]
                amt=float(tx["amount"])
                fee=float(tx.get("fee_burned",0.0))
                ledger[to_thr]=round(ledger.get(to_thr,0.0)+amt,6)
                ledger[BURN_ADDRESS]=round(ledger.get(BURN_ADDRESS,0.0)+fee,6)
        save_json(LEDGER_FILE,ledger)

    # reward to ledger
    ledger=load_json(LEDGER_FILE,{})
    ledger[thr_address]=round(ledger.get(thr_address,0.0)+miner_share,6)
    ledger[AI_WALLET_ADDRESS]=round(ledger.get(AI_WALLET_ADDRESS,0.0)+ai_share,6)
    ledger[BURN_ADDRESS]=round(ledger.get(BURN_ADDRESS,0.0)+burn_share,6)
    save_json(LEDGER_FILE,ledger)

    save_json(CHAIN_FILE,chain)
    update_last_block(new_block,is_block=True)
    print(f"⛏️ Miner {thr_address} found block #{height}! R={total_reward} (m/a/b: {miner_share}/{ai_share}/{burn_share}) | TXs: {len(included)} | Stratum={is_stratum}")
    return jsonify(status="accepted", height=height, reward=miner_share, tx_included=len(included)),200


# ─── BACKGROUND MINTER / WATCHDOG ──────────────────
def submit_mining_block_for_pledge(thr_addr):
    chain = load_json(CHAIN_FILE, [])

    pow_blocks = [
        b for b in chain
        if isinstance(b, dict) and b.get("reward") is not None
    ]

    if pow_blocks:
        prev_hash = pow_blocks[-1].get("block_hash", "0"*64)
        local_height = len(pow_blocks)
    else:
        prev_hash = "0"*64
        local_height = 0

    height       = HEIGHT_OFFSET + local_height
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
        "is_stratum": False,
    }
    chain.append(new_block)

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
                ledger[tx["to"]] = round(ledger.get(tx["to"], 0.0) + float(tx["amount"]), 6)
                ledger[BURN_ADDRESS] = round(ledger.get(BURN_ADDRESS, 0.0) + float(tx.get("fee_burned", 0.0)), 6)
        save_json(LEDGER_FILE, ledger)

    ledger = load_json(LEDGER_FILE, {})
    ledger[thr_addr] = round(ledger.get(thr_addr, 0.0) + miner_share, 6)
    ledger[AI_WALLET_ADDRESS] = round(ledger.get(AI_WALLET_ADDRESS, 0.0) + ai_share, 6)
    ledger[BURN_ADDRESS] = round(ledger.get(BURN_ADDRESS, 0.0) + burn_share, 6)
    save_json(LEDGER_FILE, ledger)

    save_json(CHAIN_FILE, chain)
    update_last_block(new_block, is_block=True)
    print(f"⛏️ [Pledge PoW] block #{height} for {thr_addr} | TXs: {len(included)} | hash={pow_hash[:16]}…")

def seconds_since_last_block()->float:
    chain=load_json(CHAIN_FILE,[])
    blocks=[b for b in chain if isinstance(b,dict) and b.get("reward") is not None]
    if not blocks:
        return 10**9
    try:
        t_fmt="%Y-%m-%d %H:%M:%S UTC"
        last_ts=datetime.strptime(blocks[-1]["timestamp"],t_fmt).timestamp()
        return time.time()-last_ts
    except Exception:
        return 10**9

def confirm_mempool_if_stuck(max_wait_sec:int=180):
    pool=load_mempool()
    if not pool:
        return
    if seconds_since_last_block()<max_wait_sec:
        return
    print("⚠️ Watchdog: Mempool stuck > 3 mins. Auto-mining block to clear TXs.")
    submit_mining_block_for_pledge(AI_WALLET_ADDRESS)

def mint_first_blocks():
    pledges=load_json(PLEDGE_CHAIN,[])
    chain=load_json(CHAIN_FILE,[])
    seen={ b.get("thr_address") for b in chain if isinstance(b,dict) and b.get("thr_address") }
    for p in pledges:
        thr=p["thr_address"]
        if thr in seen:
            continue
        submit_mining_block_for_pledge(thr)


# ─── AI KNOWLEDGE WATCHER – log -> mempool -> block ─────────────────────────
def ai_knowledge_watcher():
    """
    Διαβάζει το AI_BLOCK_LOG_FILE (ai_block_log.json) και για κάθε νέα
    εγγραφή δημιουργεί mempool TX τύπου 'ai_knowledge'.
    Τα TXs αυτά θα μπουν στο επόμενο block που θα γίνει mined.
    """
    try:
        log_entries = load_json(AI_BLOCK_LOG_FILE, [])
        if not log_entries:
            return

        pool = load_mempool()
        chain = load_json(CHAIN_FILE, [])

        seen_ids = set(
            tx.get("ai_log_id") for tx in pool
            if isinstance(tx, dict) and tx.get("type") == "ai_knowledge"
        )
        for tx in chain:
            if isinstance(tx, dict) and tx.get("type") == "ai_knowledge":
                if tx.get("ai_log_id"):
                    seen_ids.add(tx["ai_log_id"])

        changed = False

        for entry in log_entries:
            eid = entry.get("id")
            if not eid or eid in seen_ids:
                continue

            if str(entry.get("status","")).lower() == "error":
                continue

            prompt = entry.get("prompt", "")
            response = entry.get("response", "")
            provider = entry.get("provider", "")
            model = entry.get("model", "")
            wallet = entry.get("wallet") or AI_WALLET_ADDRESS
            ts = entry.get("timestamp") or time.strftime(
                "%Y-%m-%d %H:%M:%S UTC", time.gmtime()
            )

            payload_obj = {
                "prompt_tail": prompt[-512:],
                "response_tail": response[-2048:],
                "provider": provider,
                "model": model,
            }
            payload_json = json.dumps(payload_obj, ensure_ascii=False)
            ai_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

            tx = {
                "type": "ai_knowledge",
                "height": None,
                "timestamp": ts,
                "from": wallet,
                "to": AI_WALLET_ADDRESS,
                "amount": 0.0,
                "fee_burned": 0.0,
                "tx_id": f"AI-{eid}",
                "ai_log_id": eid,
                "ai_hash": ai_hash,
                "ai_payload": payload_json,
                "status": "pending",
                "confirmation_policy": "FAST",
                "min_signers": 0,
            }

            pool.append(tx)
            seen_ids.add(eid)
            changed = True

        if changed:
            save_mempool(pool)
            print("🤖 [AI-KNOWLEDGE] updated mempool with new AI entries.")

    except Exception as e:
        print("[AI-KNOWLEDGE WATCHER] error:", e)


# ─── SCHEDULER ─────────────────────────────────────
scheduler=BackgroundScheduler(daemon=True)
scheduler.add_job(mint_first_blocks, "interval", minutes=1)
scheduler.add_job(confirm_mempool_if_stuck, "interval", seconds=45)
scheduler.add_job(aggregator_step, "interval", seconds=10)
scheduler.add_job(ai_knowledge_watcher, "interval", seconds=30)  # NEW
scheduler.start()

# Run AI Wallet Check on Startup
ensure_ai_wallet()
recompute_height_offset_from_ledger()  # <-- Initialize offset

if __name__=="__main__":
    port=int(os.getenv("PORT",3333))
    app.run(host="0.0.0.0", port=port)
