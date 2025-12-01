import os
import json
import time
import hashlib
import logging
import requests

from flask import (
    Flask, request, jsonify,
    render_template, send_from_directory,
    redirect, url_for
)
from phantom_gateway_mainnet import get_btc_txns
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from apscheduler.schedulers.background import BackgroundScheduler

# ─── CONFIG ───
app = Flask(__name__)
STATIC_DIR    = os.path.join(app.root_path, "static")
DATA_DIR      = os.path.join(app.root_path, "data")
LEDGER_FILE   = os.path.join(DATA_DIR, "ledger.json")
CHAIN_FILE    = os.path.join(DATA_DIR, "phantom_tx_chain.json")
PLEDGE_CHAIN  = os.path.join(DATA_DIR, "pledge_chain.json")
BTC_RECEIVER  = "1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ"
MIN_AMOUNT    = 0.00001
CONTRACTS_DIR = os.path.join(STATIC_DIR, "contracts")
os.makedirs(CONTRACTS_DIR, exist_ok=True)

# ─── LOGGER ───
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pledge")

# ─── HELPERS ───
def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def calculate_reward(height: int) -> float:
    halvings = height // 210000
    return round(1.0 / (2 ** halvings), 6)

def create_pdf_contract(btc_addr, pledge_text, thr_addr, filename):
    out = os.path.join(CONTRACTS_DIR, filename)
    c = canvas.Canvas(out, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 18)
    c.drawString(1*inch, h - 1*inch, "THRONOS BLOCKCHAIN CONTRACT")
    c.setFont("Helvetica", 12)
    c.drawString(1*inch, h - 1.5*inch, f"BTC Address: {btc_addr}")
    c.drawString(1*inch, h - 1.8*inch, "Pledge Text:")
    text = c.beginText(1*inch, h - 2.1*inch)
    text.setFont("Helvetica", 12)
    line = ""
    for word in pledge_text.split():
        if len(line) + len(word) + 1 <= 80:
            line += (" " + word if line else word)
        else:
            text.textLine(line)
            line = word
    if line:
        text.textLine(line)
    c.drawText(text)
    y_offset = (len(pledge_text) // 80 + 2) * 15
    c.drawString(1*inch, h - 2.1*inch - y_offset, f"Generated THR Address: {thr_addr}")
    c.save()
    return out

# ─── ROUTES ───
@app.route("/")
def home(): return render_template("index.html")

@app.route("/docs")
def docs(): return render_template("tokenomics.html")

@app.route("/pledge")
def pledge_form(): return render_template("pledge_form.html")

@app.route("/send")
def send_form(): return render_template("send_thr_form.html")

@app.route("/viewer")
def viewer(): return render_template("thronos_block_viewer.html")

@app.route("/wallet")
def wallet_page(): return render_template("wallet_viewer.html")

@app.route("/contracts/<path:filename>")
def serve_contract(filename):
    return send_from_directory(CONTRACTS_DIR, filename)

@app.route("/pledge_submit", methods=["POST"])
def pledge_submit():
    data        = request.get_json() or {}
    btc_address = data.get("btc_address", "").strip()
    pledge_text = data.get("pledge_text", "").strip()
    if not btc_address:
        return jsonify(error="Missing BTC address"), 400

    pledges = load_json(PLEDGE_CHAIN, [])
    exists  = next((p for p in pledges if p["btc_address"] == btc_address), None)
    if exists:
        return jsonify(
            status="already_verified",
            thr_address=exists["thr_address"],
            pledge_hash=exists["pledge_hash"],
            pdf_filename=f"pledge_{exists['thr_address']}.pdf"
        ), 200

    txns = get_btc_txns(btc_address, BTC_RECEIVER)
    logger.info("get_btc_txns for %s → %s", btc_address, txns)
    paid = any(tx["to"] == BTC_RECEIVER and tx["amount_btc"] >= MIN_AMOUNT for tx in txns)
    if not paid:
        return jsonify(status="pending", message="Waiting for BTC payment", txns=txns), 200

    thr_addr = f"THR{int(time.time()*1000)}"
    phash    = hashlib.sha256((btc_address + pledge_text).encode()).hexdigest()
    pledges.append({
        "btc_address": btc_address,
        "pledge_text": pledge_text,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "pledge_hash": phash,
        "thr_address": thr_addr
    })
    save_json(PLEDGE_CHAIN, pledges)
    pdf_name = f"pledge_{thr_addr}.pdf"
    create_pdf_contract(btc_address, pledge_text, thr_addr, pdf_name)
    return jsonify(status="verified", thr_address=thr_addr, pledge_hash=phash, pdf_filename=pdf_name), 200

@app.route("/chain")
def get_chain(): return jsonify(load_json(CHAIN_FILE, [])), 200

@app.route("/last_block_hash")
def last_block_hash():
    chain = load_json(CHAIN_FILE, [])
    return jsonify(last_hash = chain[-1]["block_hash"] if chain else "0"*64)

@app.route("/submit_block", methods=["POST"])
def submit_block():
    data = request.get_json() or {}
    chain = load_json(CHAIN_FILE, [])
    h = len(chain)
    r = calculate_reward(h)
    fee = 0.005
    data.setdefault("timestamp", time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()))
    data.setdefault("block_hash", f"THR-{h}")
    data["reward"] = r
    data["pool_fee"] = fee
    data["reward_to_miner"] = round(r - fee, 6)

    pledges = load_json(PLEDGE_CHAIN, [])
    match = next((p for p in pledges if p.get("thr_address") == data["thr_address"]), None)
    if match:
        data.update({
            "miner_btc_address": match.get("btc_address"),
            "pledge_text": match.get("pledge_text"),
            "pledge_hash": match.get("pledge_hash")
        })

    chain.append(data)
    save_json(CHAIN_FILE, chain)
    ledger = load_json(LEDGER_FILE, {})
    miner = data["thr_address"]
    ledger[miner] = round(ledger.get(miner, 0.0) + data["reward_to_miner"], 6)
    save_json(LEDGER_FILE, ledger)
    return jsonify(status="ok", **data), 200

@app.route("/wallet_data/<thr_addr>")
def wallet_data(thr_addr):
    ledger  = load_json(LEDGER_FILE, {})
    chain   = load_json(CHAIN_FILE, [])
    bal     = round(ledger.get(thr_addr, 0.0), 6)
    history = [tx for tx in chain if isinstance(tx, dict) and (tx.get("from") == thr_addr or tx.get("to") == thr_addr)]
    return jsonify(balance=bal, transactions=history), 200

@app.route("/wallet/<thr_addr>")
def wallet_redirect(thr_addr):
    return redirect(url_for("wallet_data", thr_addr=thr_addr)), 302

@app.route("/send_token", methods=["POST"])
def send_token():
    data = request.get_json() or {}
    frm  = data.get("from","").strip()
    to_  = data.get("to","").strip()
    try:
        amt = round(float(data.get("amount",0)),6)
    except:
        return jsonify(error="Invalid amount"), 400
    if not frm or not to_ or amt<=0:
        return jsonify(error="Invalid input"), 400

    ledger = load_json(LEDGER_FILE,{})
    fee    = 0.0015
    total  = round(amt+fee,6)
    if ledger.get(frm,0.0) < total:
        return jsonify(error="Insufficient balance"), 403

    ledger[frm] = round(ledger.get(frm,0.0)-total,6)
    ledger[to_] = round(ledger.get(to_,0.0)+amt,6)
    save_json(LEDGER_FILE, ledger)
    tx = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "from": frm, "to": to_, "amount": amt, "fee": fee
    }
    chain = load_json(CHAIN_FILE, [])
    chain.append(tx)
    save_json(CHAIN_FILE, chain)
    return jsonify(status="OK", tx=tx), 200

# ─── BACKGROUND ───
def mint_first_blocks():
    pledges = load_json(PLEDGE_CHAIN, [])
    chain   = load_json(CHAIN_FILE, [])
    seen    = {b.get("thr_address") for b in chain if isinstance(b, dict) and b.get("thr_address")}
    height  = len(chain)
    for p in pledges:
        thr = p["thr_address"]
        if thr in seen:
            continue
        r   = calculate_reward(height)
        fee = 0.005
        to_miner = round(r - fee, 6)
        block = {
            "thr_address": thr,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "block_hash": f"THR-{height}",
            "reward": r,
            "pool_fee": fee,
            "reward_to_miner": to_miner
        }
        try:
            requests.post(f"http://localhost:{os.getenv('PORT',8000)}/submit_block", json=block, timeout=5).raise_for_status()
            chain = load_json(CHAIN_FILE, [])
            height = len(chain)
            seen.add(thr)
            print(f"⛏️ Mined block #{height} for {thr}: +{to_miner} THR")
        except Exception as e:
            print(f"❌ Failed mining for {thr}:", e)

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(mint_first_blocks, 'interval', minutes=1)
scheduler.start()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3333))
    app.run(host="0.0.0.0", port=port, debug=True)
