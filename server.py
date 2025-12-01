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

import os
import json
import time
import hashlib
import logging
import secrets

import requests
from flask import (
    Flask, request, jsonify,
    render_template, send_from_directory,
    redirect, url_for
)
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler

from phantom_gateway_mainnet import get_btc_txns
from secure_pledge_embed import create_secure_pdf_contract
from phantom_decode import decode_payload_from_image

# ─── CONFIG ────────────────────────────────────────
app = Flask(__name__)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Railway volume → /app/data
# Ensure DATA_DIR is persistent. If run locally, it will be under current dir/data.
# On Railway, mount a volume to /app/data.
DATA_DIR   = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

LEDGER_FILE   = os.path.join(DATA_DIR, "ledger.json")
CHAIN_FILE    = os.path.join(DATA_DIR, "phantom_tx_chain.json")
PLEDGE_CHAIN  = os.path.join(DATA_DIR, "pledge_chain.json")

# κρατάμε πάντα μια σύνοψη του τελευταίου block/tx
LAST_BLOCK_FILE = os.path.join(DATA_DIR, "last_block.json")

# Whitelist για free pledges (χωρίς BTC)
WHITELIST_FILE = os.path.join(DATA_DIR, "free_pledge_whitelist.json")
ADMIN_SECRET   = os.getenv("ADMIN_SECRET", "CHANGE_ME_NOW")

BTC_RECEIVER  = "1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ"
MIN_AMOUNT    = 0.00001

# ΣΗΜΑΝΤΙΚΟ: Τα contracts (PDF/PNG) στο DATA_DIR (volume) – ΔΕΝ χάνονται σε redeploy
CONTRACTS_DIR = os.path.join(DATA_DIR, "contracts")
os.makedirs(CONTRACTS_DIR, exist_ok=True)

SEND_FEE = 0.0015  # THR fee που καίγεται σε κάθε send
MINING_DIFFICULTY = 5 # Number of leading zeros required for PoW

# New Fee Distribution Config
AI_WALLET_ADDRESS = "THR_AI_AGENT_WALLET_V1"
BURN_ADDRESS = "0x0"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pledge")


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


def calculate_reward(height: int) -> float:
    halvings = height // 210000
    return round(1.0 / (2 ** halvings), 6)


def update_last_block(entry, is_block=True):
    """
    Γράφει μια μικρή σύνοψη του τελευταίου block/tx στο LAST_BLOCK_FILE,
    ώστε ο viewer & το home να έχουν πάντα status ακόμη κι αν το chain
    αδειάσει κάποτε.
    """
    summary = {
        "height": entry.get("height"),
        "block_hash": entry.get("block_hash") or entry.get("tx_id"),
        "timestamp": entry.get("timestamp"),
        "thr_address": entry.get("thr_address"),
        "type": "block" if is_block else entry.get("type", "transfer"),
    }
    save_json(LAST_BLOCK_FILE, summary)

def verify_btc_payment(btc_address, min_amount):
    """
    Placeholder for Watcher logic.
    In the future, this function will:
    1. Check the BTC network for transactions to BTC_RECEIVER from btc_address.
    2. Verify confirmations.
    3. Return True if payment is verified.
    """
    # TODO: Implement actual BTC node connection or robust API check here.
    # For now, we rely on phantom_gateway_mainnet.get_btc_txns called in pledge_submit
    pass

# ─── BASIC PAGES ───────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/contracts/<path:filename>")
def serve_contract(filename):
    # Σερβίρει PDF + PNG από data/contracts (volume)
    return send_from_directory(CONTRACTS_DIR, filename)


@app.route("/viewer")
def viewer():
    return render_template("thronos_block_viewer.html")


@app.route("/wallet")
def wallet_page():
    return render_template("wallet_viewer.html")


@app.route("/send")
def send_page():
    return render_template("send.html")


# ─── RECOVERY FLOW ─────────────────────────────────
@app.route("/recovery")
def recovery_page():
    return render_template("recovery.html")


@app.route("/recover_submit", methods=["POST"])
def recover_submit():
    if 'file' not in request.files:
        return jsonify(error="No file part"), 400
    file = request.files['file']
    passphrase = request.form.get('passphrase', '').strip()
    
    if file.filename == '':
        return jsonify(error="No selected file"), 400
    
    if not passphrase:
        return jsonify(error="Passphrase is required"), 400
    
    if file:
        filename = secure_filename(file.filename)
        # Save temporarily in DATA_DIR to avoid permission issues
        temp_path = os.path.join(DATA_DIR, f"temp_{int(time.time())}_{filename}")
        try:
            file.save(temp_path)
            
            # Attempt decode with passphrase
            payload = decode_payload_from_image(temp_path, passphrase)
            
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            if payload:
                return jsonify(status="success", payload=payload), 200
            else:
                return jsonify(error="Failed to decode or decrypt. Check your file and passphrase."), 400
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify(error=f"Server error: {str(e)}"), 500
            
    return jsonify(error="Unknown error"), 500


# ─── STATUS APIs (για home + viewer) ───────────────
@app.route("/chain")
def get_chain():
    return jsonify(load_json(CHAIN_FILE, [])), 200


@app.route("/last_block")
def api_last_block():
    """
    Επιστρέφει σύνοψη τελευταίου block/tx από last_block.json.
    Αν δεν υπάρχει ακόμα, γυρνάει κενό dict.
    """
    summary = load_json(LAST_BLOCK_FILE, {})
    return jsonify(summary), 200


@app.route("/last_block_hash")
def last_block_hash():
    chain = load_json(CHAIN_FILE, [])
    # μόνο κανονικά blocks (όχι transfers)
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
    """
    Provides all necessary info for miners/proxy:
    - difficulty (leading zeros)
    - target (hex target)
    - nbits (compact target)
    - last_hash
    """
    chain = load_json(CHAIN_FILE, [])
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    
    if blocks:
        last_hash = blocks[-1].get("block_hash", "")
    else:
        last_hash = "0" * 64

    # Calculate Target from Difficulty
    # Difficulty 5 means target is 00000FFFFF... (256 bits)
    # This is a simplification. Real target calculation is more complex.
    # For our MVP:
    target_int = int("F" * (64 - MINING_DIFFICULTY), 16)
    target_hex = f"{target_int:064x}"
    
    # Fake nbits for Stratum (usually 4 bytes)
    # We'll just use a placeholder that the proxy can read
    nbits = "1d00ffff" 

    return jsonify({
        "difficulty": MINING_DIFFICULTY,
        "difficulty_int": 1, # Stratum difficulty (1 = simplest)
        "target": target_hex,
        "last_hash": last_hash,
        "nbits": nbits
    }), 200


# ─── PLEDGE FLOW ───────────────────────────────────
@app.route("/pledge")
def pledge_form():
    return render_template("pledge_form.html")


@app.route("/pledge_submit", methods=["POST"])
def pledge_submit():
    data = request.get_json() or {}
    btc_address = (data.get("btc_address") or "").strip()
    pledge_text = (data.get("pledge_text") or "").strip()
    passphrase  = (data.get("passphrase") or "").strip()  # Optional passphrase

    if not btc_address:
        return jsonify(error="Missing BTC address"), 400

    pledges = load_json(PLEDGE_CHAIN, [])
    exists = next((p for p in pledges if p["btc_address"] == btc_address), None)
    if exists:
        # Ήδη υπάρχει pledge για αυτό το BTC.
        return jsonify(
            status="already_verified",
            thr_address=exists["thr_address"],
            pledge_hash=exists["pledge_hash"],
            pdf_filename=exists.get("pdf_filename", f"pledge_{exists['thr_address']}.pdf"),
            # send_secret ΔΕΝ το ξαναδίνουμε εδώ
        ), 200

    # --- BTC verification ή free mode με whitelist ---
    free_list   = load_json(WHITELIST_FILE, [])
    is_dev_free = btc_address in free_list

    if is_dev_free:
        paid = True
        txns = []
    else:
        txns = get_btc_txns(btc_address, BTC_RECEIVER)
        paid = any(
            tx["to"] == BTC_RECEIVER and tx["amount_btc"] >= MIN_AMOUNT
            for tx in txns
        )

    if not paid:
        return jsonify(
            status="pending",
            message="Waiting for BTC payment",
            txns=txns,
        ), 200

    # Δημιουργία THR address + pledge hash
    thr_addr = f"THR{int(time.time() * 1000)}"
    phash = hashlib.sha256((btc_address + pledge_text).encode()).hexdigest()

    # Send seed (seed phrase για /send_thr)
    send_seed      = secrets.token_hex(16)  # 32 hex chars
    send_seed_hash = hashlib.sha256(send_seed.encode()).hexdigest()
    
    # Υπολογισμός send_auth_hash με υποστήριξη passphrase
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
        "has_passphrase": bool(passphrase) # Flag για να ξέρουμε αν απαιτείται passphrase
    }

    # Ύψος chain για το QR / secure PDF
    chain  = load_json(CHAIN_FILE, [])
    height = len(chain)

    # Δημιουργία secure PDF (AES + QR + stego PNG, με send_seed)
    # Pass the passphrase for encryption
    pdf_name = create_secure_pdf_contract(
        btc_address=btc_address,
        pledge_text=pledge_text,
        thr_address=thr_addr,
        pledge_hash=phash,
        height=height,
        send_seed=send_seed,
        output_dir=CONTRACTS_DIR,
        passphrase=passphrase 
    )

    # κρατάμε και το filename πίσω στο pledge
    pledge_entry["pdf_filename"] = pdf_name
    pledges.append(pledge_entry)
    save_json(PLEDGE_CHAIN, pledges)

    return jsonify(
        status="verified",
        thr_address=thr_addr,
        pledge_hash=phash,
        pdf_filename=pdf_name,
        send_secret=send_seed,  # ΜΟΝΟ στον client (σαν seed)
    ), 200


# ─── WALLET APIS ───────────────────────────────────
@app.route("/wallet_data/<thr_addr>")
def wallet_data(thr_addr):
    ledger  = load_json(LEDGER_FILE, {})
    chain   = load_json(CHAIN_FILE, [])
    bal     = round(float(ledger.get(thr_addr, 0.0)), 6)

    history = [
        tx for tx in chain
        if isinstance(tx, dict) and (
            tx.get("from") == thr_addr or tx.get("to") == thr_addr
        )
    ]
    return jsonify(balance=bal, transactions=history), 200


@app.route("/wallet/<thr_addr>")
def wallet_redirect(thr_addr):
    return redirect(url_for("wallet_data", thr_addr=thr_addr)), 302


# ─── SEND THR (auth_secret = send_seed από PDF/stego) ─────
@app.route("/send_thr", methods=["POST"])
def send_thr():
    data = request.get_json() or {}

    from_thr    = (data.get("from_thr") or "").strip()
    to_thr      = (data.get("to_thr") or "").strip()
    amount_raw  = data.get("amount", 0)
    auth_secret = (data.get("auth_secret") or "").strip()  # εδώ βάζει ο χρήστης το seed
    passphrase  = (data.get("passphrase") or "").strip()   # Optional passphrase

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

    pledges = load_json(PLEDGE_CHAIN, [])
    sender_pledge = next(
        (p for p in pledges if p.get("thr_address") == from_thr),
        None
    )
    if not sender_pledge:
        return jsonify(error="unknown_sender_thr"), 404

    stored_auth_hash = sender_pledge.get("send_auth_hash")
    if not stored_auth_hash:
        return jsonify(error="send_not_enabled_for_this_thr"), 400

    # auth_secret = send_seed -> hash για auth
    # Check if passphrase is required/provided and construct auth string accordingly
    if sender_pledge.get("has_passphrase"):
        if not passphrase:
             return jsonify(error="passphrase_required"), 400
        auth_string = f"{auth_secret}:{passphrase}:auth"
    else:
        auth_string = f"{auth_secret}:auth"

    auth_hash = hashlib.sha256(auth_string.encode()).hexdigest()
    
    if auth_hash != stored_auth_hash:
        return jsonify(error="invalid_auth"), 403

    ledger = load_json(LEDGER_FILE, {})
    sender_balance   = float(ledger.get(from_thr, 0.0))
    receiver_balance = float(ledger.get(to_thr, 0.0))

    total_cost = amount + SEND_FEE
    if sender_balance < total_cost:
        return jsonify(
            error="insufficient_balance",
            balance=round(sender_balance, 6),
        ), 400

    sender_balance   = round(sender_balance - total_cost, 6)
    receiver_balance = round(receiver_balance + amount, 6)
    ledger[from_thr] = sender_balance
    ledger[to_thr]   = receiver_balance
    save_json(LEDGER_FILE, ledger)

    chain = load_json(CHAIN_FILE, [])
    height = len(chain)
    tx = {
        "type": "transfer",
        "height": height,
        "timestamp": time.strftime(
            "%Y-%m-%d %H:%M:%S UTC",
            time.gmtime(),
        ),
        "from": from_thr,
        "to": to_thr,
        "amount": round(amount, 6),
        "fee_burned": SEND_FEE,
        "tx_id": f"TX-{height}-{int(time.time())}",
        "thr_address": from_thr,
    }
    chain.append(tx)
    save_json(CHAIN_FILE, chain)

    # ενημερώνουμε last_block.json (εδώ τύπου transfer)
    update_last_block(tx, is_block=False)

    return jsonify(
        status="ok",
        tx=tx,
        new_balance_from=sender_balance,
        new_balance_to=receiver_balance,
    ), 200


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
    """
    Migration για ΠΑΛΙΑ pledges:

    - βρίσκει entries χωρίς send_seed_hash
    - δημιουργεί send_seed, send_seed_hash, send_auth_hash
    - ξαναφτιάχνει PDF με stego fire + seed
    - επιστρέφει {thr_address, btc_address, send_seed, pdf_filename}
      για να κρατήσεις τα νέα seeds.
    """

    payload = request.get_json() or {}
    secret = request.args.get("secret", "") or payload.get("secret", "")
    if secret != ADMIN_SECRET:
        return jsonify(error="forbidden"), 403

    pledges = load_json(PLEDGE_CHAIN, [])
    changed = []

    for p in pledges:
        if p.get("send_seed_hash") and p.get("send_auth_hash"):
            continue  # ήδη migrated

        thr_addr    = p["thr_address"]
        btc_address = p["btc_address"]
        pledge_text = p["pledge_text"]
        pledge_hash = p["pledge_hash"]

        send_seed      = secrets.token_hex(16)
        send_seed_hash = hashlib.sha256(send_seed.encode()).hexdigest()
        send_auth_hash = hashlib.sha256(f"{send_seed}:auth".encode()).hexdigest()

        p["send_seed_hash"] = send_seed_hash
        p["send_auth_hash"] = send_auth_hash
        p["has_passphrase"] = False # Migration assumes no passphrase for old pledges

        chain  = load_json(CHAIN_FILE, [])
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

        changed.append({
            "thr_address": thr_addr,
            "btc_address": btc_address,
            "send_seed": send_seed,
            "pdf_filename": pdf_name,
        })

    save_json(PLEDGE_CHAIN, pledges)
    return jsonify(migrated=changed), 200


# ─── MINING ENDPOINT ───────────────────────────────
@app.route("/submit_block", methods=["POST"])
def submit_block():
    """
    Accepts PoW submissions from miners.
    Requires: thr_address, nonce, pow_hash, prev_hash
    """
    data = request.get_json() or {}
    thr_address = data.get("thr_address")
    nonce = data.get("nonce")
    pow_hash = data.get("pow_hash")
    prev_hash = data.get("prev_hash")
    
    if not all([thr_address, nonce is not None, pow_hash, prev_hash]):
        return jsonify(error="Missing mining data"), 400
        
    # 1. Verify last hash matches current chain tip
    chain = load_json(CHAIN_FILE, [])
    # Get last block (filter out transfers if needed, or just take last entry)
    # For simplicity, we check against what the miner claims is prev_hash
    # In production, we must strictly check against server's actual last block hash
    
    blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]
    if blocks:
        server_last_hash = blocks[-1].get("block_hash", "")
    else:
        server_last_hash = "0" * 64
        
    if prev_hash != server_last_hash:
        return jsonify(error="Stale block (prev_hash mismatch)"), 400
        
    # 2. Verify PoW
    # Re-calculate hash: sha256(prev_hash + thr_address + nonce)
    nonce_str = str(nonce).encode()
    check_data = (prev_hash + thr_address).encode() + nonce_str
    check_hash = hashlib.sha256(check_data).hexdigest()
    
    if check_hash != pow_hash:
        return jsonify(error="Invalid hash calculation"), 400
        
    # 3. Verify Difficulty
    # Hardcoded difficulty 5 for now (must match miner)
    DIFFICULTY = 5
    if not check_hash.startswith("0" * DIFFICULTY):
        return jsonify(error=f"Insufficient difficulty (needs {DIFFICULTY} zeros)"), 400
        
    # 4. Reward Distribution
    height = len(chain)
    total_reward = calculate_reward(height)
    
    # New Split:
    # 80% to Miner
    # 10% to AI Agent
    # 10% Burned
    
    miner_share = round(total_reward * 0.80, 6)
    ai_share    = round(total_reward * 0.10, 6)
    burn_share  = round(total_reward * 0.10, 6)
    
    new_block = {
        "thr_address": thr_address,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "block_hash": pow_hash,
        "prev_hash": prev_hash,
        "nonce": nonce,
        "reward": total_reward,
        "reward_split": {
            "miner": miner_share,
            "ai": ai_share,
            "burn": burn_share
        },
        "height": height,
        "type": "block"
    }
    
    chain.append(new_block)
    save_json(CHAIN_FILE, chain)
    
    # Update Ledger
    ledger = load_json(LEDGER_FILE, {})
    
    # Miner gets 80%
    ledger[thr_address] = round(ledger.get(thr_address, 0.0) + miner_share, 6)
    
    # AI Agent gets 10%
    ledger[AI_WALLET_ADDRESS] = round(ledger.get(AI_WALLET_ADDRESS, 0.0) + ai_share, 6)
    
    # Burn address gets 10% (optional, but good for tracking)
    ledger[BURN_ADDRESS] = round(ledger.get(BURN_ADDRESS, 0.0) + burn_share, 6)
    
    save_json(LEDGER_FILE, ledger)
    
    # Update Last Block Summary
    update_last_block(new_block, is_block=True)
    
    print(f"⛏️  Miner {thr_address} found block #{height}! Reward: {total_reward} THR (Miner: {miner_share}, AI: {ai_share}, Burn: {burn_share})")
    
    return jsonify(status="accepted", height=height, reward=miner_share), 200


# ─── BACKGROUND MINTER ─────────────────────────────
def submit_mining_block_for_pledge(thr_addr):
    """
    Μικρό helper ώστε να βάζουμε σωστό height + last_block update
    όταν ο background miner κάνει auto-mint blocks για τα pledges.
    """
    chain = load_json(CHAIN_FILE, [])
    height = len(chain)
    r   = calculate_reward(height)
    # Pledge blocks might follow different rules, but let's apply fee here too for consistency or keep it simple
    # For pledge blocks, let's keep original logic or apply small fee
    fee = 0.005
    to_miner = round(r - fee, 6)

    block = {
        "thr_address": thr_addr,
        "timestamp": time.strftime(
            "%Y-%m-%d %H:%M:%S UTC",
            time.gmtime(),
        ),
        "block_hash": f"THR-{height}",
        "reward": r,
        "pool_fee": fee,
        "reward_to_miner": to_miner,
        "height": height,
    }

    chain.append(block)
    save_json(CHAIN_FILE, chain)

    ledger = load_json(LEDGER_FILE, {})
    ledger[thr_addr] = round(ledger.get(thr_addr, 0.0) + to_miner, 6)
    save_json(LEDGER_FILE, ledger)

    update_last_block(block, is_block=True)
    print(f"⛏️ Auto-mined block #{height} for {thr_addr}: +{to_miner} THR")


def mint_first_blocks():
    pledges = load_json(PLEDGE_CHAIN, [])
    chain   = load_json(CHAIN_FILE, [])
    seen    = {
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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3333))
    app.run(host="0.0.0.0", port=port)
