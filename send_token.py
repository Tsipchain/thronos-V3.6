
import json, time
from flask import request, jsonify

LEDGER_FILE = "ledger.json"
CHAIN_FILE = "phantom_tx_chain.json"
TX_FEE = 0.0015  # Flat fee per transfer

def load_ledger():
    try:
        with open(LEDGER_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_ledger(ledger):
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=2)

def handle_token_send():
    data = request.get_json()
    sender = data.get("from")
    recipient = data.get("to")
    amount = float(data.get("amount", 0))

    if not sender or not recipient or amount <= 0:
        return jsonify({"error": "Invalid input"}), 400

    ledger = load_ledger()

    sender_balance = ledger.get(sender, 0)
    total_required = amount + TX_FEE

    if sender_balance < total_required:
        return jsonify({"error": "Insufficient balance"}), 403

    # Execute transfer
    ledger[sender] -= total_required
    ledger[recipient] = ledger.get(recipient, 0) + amount
    save_ledger(ledger)

    tx = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "from": sender,
        "to": recipient,
        "amount": amount,
        "fee": TX_FEE,
        "type": "transfer"
    }

    try:
        with open(CHAIN_FILE, "r") as f:
            chain = json.load(f)
    except:
        chain = []

    chain.append(tx)
    with open(CHAIN_FILE, "w") as f:
        json.dump(chain, f, indent=2)

    return jsonify({
        "status": "success",
        "tx": tx,
        "new_balance": ledger[sender]
    })
