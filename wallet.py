
import json
from flask import jsonify

LEDGER_FILE = "ledger.json"
CHAIN_FILE = "phantom_tx_chain.json"

def handle_wallet_view(thr_address):
    # Υπόλοιπο
    try:
        with open(LEDGER_FILE, "r") as f:
            ledger = json.load(f)
    except:
        ledger = {}

    balance = ledger.get(thr_address, 0)

    # Συναλλαγές
    try:
        with open(CHAIN_FILE, "r") as f:
            chain = json.load(f)
    except:
        chain = []

    txs = [tx for tx in chain if isinstance(tx, dict) and (
        tx.get("from") == thr_address or tx.get("to") == thr_address)]

    return jsonify({
        "balance": round(balance, 6),
        "transactions": txs
    })
