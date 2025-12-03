# quorum_agent.py
import os, json, time, hashlib
import requests

from quorum_crypto import BLS

SERVER = os.getenv("THRONOS_URL", "https://thrchain.up.railway.app")
KEY_FILE = os.getenv("AGENT_KEY_FILE", "agent_key.json")
SIGNER_TAG = os.getenv("SIGNER_TAG", "AI_QUORUM_NODE")

def load_or_create_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r") as f:
            data = json.load(f)
            return data["sk"], data["pk"]
    if not BLS.available():
        raise RuntimeError("BLS not available (pip install blspy)")
    # ΔΗΜΙΟΥΡΓΗΣΕ πραγματικό τυχαίο seed στην πράξη
    sk = BLS.generate_key()[0]
    pk = BLS.generate_key()[1]  # μικρό hack για να κρατήσω interface – καλύτερα κράτα το pk από την ίδια κλήση
    # Διόρθωση: πάρε sk->pk σωστά:
    sk_hex = sk
    # derive pk from sk
    from blspy import PrivateKey
    pk_hex = PrivateKey.from_bytes(bytes.fromhex(sk_hex)).get_g1().serialize().hex()
    with open(KEY_FILE, "w") as f:
        json.dump({"sk": sk_hex, "pk": pk_hex}, f, indent=2)
    return sk_hex, pk_hex

def tx_message_bytes(tx: dict) -> bytes:
    material = f"{tx.get('from','')}|{tx.get('to','')}|{tx.get('amount',0)}|{tx.get('tx_id','')}"
    return hashlib.sha256(material.encode()).digest()

def main_loop():
    sk, pk = load_or_create_key()
    while True:
        try:
            mem = requests.get(f"{SERVER}/api/mempool", timeout=10).json()
            for tx in mem:
                # Αν είναι ήδη confirmed skip
                if tx.get("status") == "confirmed":
                    continue
                # Αν έχουμε ήδη υπογράψει (με βάση pubkeys στο tx) skip
                if pk in (tx.get("pubkeys") or []):
                    continue
                msg = tx_message_bytes(tx)
                sig_hex = BLS.sign(msg, sk)
                payload = {
                    "tx_id": tx["tx_id"],
                    "signer": SIGNER_TAG,
                    "partial_sig": sig_hex,
                    "pubkey": pk,
                    "scheme": "BLS"
                }
                r = requests.post(f"{SERVER}/api/attest", json=payload, timeout=10)
                try:
                    j = r.json()
                except Exception:
                    j = {"status": r.status_code}
                print("[agent]", tx["tx_id"], j)
        except Exception as e:
            print("agent error:", e)

        time.sleep(5)

if __name__ == "__main__":
    main_loop()
