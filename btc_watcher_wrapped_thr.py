
import requests
import json
from datetime import datetime

# ΠΡΟΣΑΡΜΟΣΕ ΑΥΤΗ ΤΗΝ ΔΙΕΥΘΥΝΣΗ BTC
btc_address = "1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ"

# Κατώφλι μικροσυναλλαγής σε BTC
threshold_btc = 0.001

# Blockstream API endpoint
url = f"https://blockstream.info/api/address/{btc_address}/txs"

print(f"Fetching transactions for {btc_address}...")

try:
    response = requests.get(url)
    response.raise_for_status()
    txs = response.json()

    wrapped = []

    for tx in txs:
        txid = tx["txid"]
        received_time = datetime.utcfromtimestamp(tx.get("status", {}).get("block_time", 0)).isoformat()
        outputs = tx.get("vout", [])

        for out in outputs:
            value_btc = out["value"] / 1e8
            scriptpubkey_address = out.get("scriptpubkey_address", "")

            if value_btc < threshold_btc and scriptpubkey_address == btc_address:
                wrapped.append({
                    "source_txid": txid,
                    "amount_btc": value_btc,
                    "received_time": received_time,
                    "wrapped_as": "wTHR",
                    "equivalent_thr": round(value_btc * 100000, 4),  # Conversion rate
                })

    with open("wrapped_thr_ledger.json", "w") as f:
        json.dump(wrapped, f, indent=2)

    print(f"✅ Saved {len(wrapped)} wrapped transactions to 'wrapped_thr_ledger.json'")

except Exception as e:
    print(f"❌ Error fetching transactions: {e}")
