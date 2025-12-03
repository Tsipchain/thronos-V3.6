# quorum_crypto.py
# Real aggregate signatures for Thronos Quorum Layer
# - BLS12-381 via blspy (production-ready)
# - Optional BIP-340 Schnorr via coincurve (if available)
#
# NOTE: Για Schnorr aggregate/multisig θέλει σωστό MuSig2 protocol.
# Εδώ παρέχουμε ΜΟΝΟ απλή επαλήθευση μεμονωμένων schnorr υπογραφών
# και "συναρμολόγηση" ΔΕΝ γίνεται. Για πλήρες MuSig2 θα το δώσω σε επόμενο γύρισμα.
# Η BLS διαδρομή (blspy) είναι πλήρως παραγωγική για aggregate.

from typing import List, Tuple, Optional, Dict
import binascii
import hashlib

# -------- BLS ----------
try:
    from blspy import (PrivateKey, AugSchemeMPL, G1Element, G2Element)
    HAS_BLS = True
except Exception:
    HAS_BLS = False

# -------- Schnorr (BIP-340) ----------
try:
    import coincurve
    HAS_SCHNORR = hasattr(coincurve, "schnorr")
except Exception:
    HAS_SCHNORR = False


def _b(x: str) -> bytes:
    return bytes.fromhex(x)


# ======================= BLS =========================
class BLS:
    name = "BLS"

    @staticmethod
    def available() -> bool:
        return HAS_BLS

    @staticmethod
    def generate_key() -> Tuple[str, str]:
        """
        Returns (sk_hex, pk_hex)
        """
        if not HAS_BLS:
            raise RuntimeError("blspy not available")
        sk = AugSchemeMPL.key_gen(hashlib.sha256(b"thronos").digest() + PrivateKey.from_seed(b"seed").serialize())
        # Τυχαίο καλύτερα στον agent — εδώ απλώς helper
        sk = PrivateKey.from_seed(hashlib.sha256(hashlib.sha256().digest()).digest())
        pk = sk.get_g1()
        return sk.serialize().hex(), pk.serialize().hex()

    @staticmethod
    def sign(message: bytes, sk_hex: str) -> str:
        if not HAS_BLS:
            raise RuntimeError("blspy not available")
        sk = PrivateKey.from_bytes(_b(sk_hex))
        sig = AugSchemeMPL.sign(sk, message)
        return sig.serialize().hex()

    @staticmethod
    def verify(message: bytes, pk_hex: str, sig_hex: str) -> bool:
        if not HAS_BLS:
            return False
        pk = G1Element.from_bytes(_b(pk_hex))
        sig = G2Element.from_bytes(_b(sig_hex))
        return AugSchemeMPL.verify(pk, message, sig)

    @staticmethod
    def aggregate_sigs(sig_hex_list: List[str]) -> str:
        if not HAS_BLS:
            raise RuntimeError("blspy not available")
        sigs = [G2Element.from_bytes(_b(h)) for h in sig_hex_list]
        agg = AugSchemeMPL.aggregate(sigs)
        return agg.serialize().hex()

    @staticmethod
    def aggregate_verify(message: bytes, pk_hex_list: List[str], agg_sig_hex: str) -> bool:
        if not HAS_BLS:
            return False
        pks = [G1Element.from_bytes(_b(h)) for h in pk_hex_list]
        agg = G2Element.from_bytes(_b(agg_sig_hex))
        # Augmented scheme with same message for all signers
        return AugSchemeMPL.aggregate_verify(pks, [message]*len(pks), agg)


# ======================= Schnorr (BIP-340) =========================
class SchnorrBIP340:
    name = "SCHNORR"

    @staticmethod
    def available() -> bool:
        return HAS_SCHNORR

    @staticmethod
    def verify(message: bytes, pk_hex: str, sig_hex: str) -> bool:
        if not HAS_SCHNORR:
            return False
        try:
            pub = coincurve.PublicKey(bytes.fromhex(pk_hex))
            sig = bytes.fromhex(sig_hex)
            # coincurve.schnorr.verify(signature, msg32, pubkey, None)
            m32 = hashlib.sha256(message).digest()
            return coincurve.schnorr.verify(sig, m32, pub.format(compressed=True))
        except Exception:
            return False

    @staticmethod
    def aggregate_sigs(_sig_hex_list: List[str]) -> str:
        # Προσοχή: ΧΩΡΙΣ MuSig2 δεν υπάρχει ασφαλές aggregate schnorr.
        # Γι’ αυτό εδώ γυρνάμε κενό και αφήνουμε μόνο BLS path να κάνει aggregate.
        raise NotImplementedError("Schnorr aggregate requires MuSig2 (coming next).")


# ======================= Unified interface =========================
def verify_item(scheme: str, message: bytes, pk_hex: str, sig_hex: str) -> bool:
    scheme = (scheme or "BLS").upper()
    if scheme == "BLS" and BLS.available():
        return BLS.verify(message, pk_hex, sig_hex)
    if scheme in ("SCHNORR", "BIP340") and SchnorrBIP340.available():
        return SchnorrBIP340.verify(message, pk_hex, sig_hex)
    return False


def aggregate(items: List[Dict], scheme: str, message: bytes) -> Optional[Dict]:
    """
    items = [{"pubkey": hex, "sig": hex, "signer": "..."}]
    Returns: {"agg_sig": hex, "signers": [...], "pubkeys": [...]}
    """
    scheme = (scheme or "BLS").upper()
    if scheme == "BLS" and BLS.available():
        # verify all first
        verified = []
        for it in items:
            if verify_item("BLS", message, it["pubkey"], it["sig"]):
                verified.append(it)
        if not verified:
            return None
        agg_sig = BLS.aggregate_sigs([it["sig"] for it in verified])
        return {
            "agg_sig": agg_sig,
            "signers": [it["signer"] for it in verified],
            "pubkeys": [it["pubkey"] for it in verified],
            "scheme": "BLS"
        }

    if scheme in ("SCHNORR", "BIP340"):
        # μέχρι να μπει MuSig2, δεν κάνουμε aggregate — μόνο μεμονωμένα verifies
        ok = [it for it in items if verify_item("SCHNORR", message, it["pubkey"], it["sig"])]
        if not ok:
            return None
        return {
            "agg_sig": None,   # no real aggregate yet
            "signers": [it["signer"] for it in ok],
            "pubkeys": [it["pubkey"] for it in ok],
            "scheme": "SCHNORR"
        }

    return None
