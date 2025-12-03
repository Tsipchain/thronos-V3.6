# musig2.py
# Lightweight MuSig2-like aggregator stub (deterministic)

import hashlib
from typing import List, Dict

def musig2_aggregate(items: List[Dict], message: bytes) -> Dict:
    """
    Stub aggregation: συνδυάζει (pubkey||sig||message) -> sha256,
    επιστρέφει agg_sig + λεξικό pubkeys/signers. Deterministic.
    """
    h = hashlib.sha256()
    pubkeys = []
    signers = []
    for it in sorted(items, key=lambda x: x.get("pubkey","")):
        pk_bytes = (it.get("pubkey","") or "").encode()
        sg = it.get("sig","") or ""
        try:
            sg_bytes = bytes.fromhex(sg)
        except Exception:
            sg_bytes = sg.encode()
        h.update(pk_bytes + sg_bytes + message)
        pubkeys.append(it.get("pubkey"))
        signers.append(it.get("signer", it.get("pubkey","")[:12]))
    agg_sig = h.hexdigest()
    return {
        "scheme": "SCHNORR",
        "agg_sig": agg_sig,
        "pubkeys": pubkeys,
        "signers": signers,
    }
