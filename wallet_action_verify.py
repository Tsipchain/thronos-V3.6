"""
wallet_action_verify — pure cryptographic verification for Thronos wallet action intents.

Extracts the stateless verification steps (1-5, 7, 8) from server_ext.py
so they can be tested without bootstrapping the monolith. Nonce management
(steps 6, 9) remains in server_ext.py because it requires persistent state.
"""

import hashlib
import json
import time

WALLET_ACTION_ALLOWED_ACTIONS = frozenset({
    'internal_transfer', 'external_send_record',
    'pool_deposit_intent', 'pool_withdraw_intent',
    'crosschain_withdraw', 'crosschain_add_liquidity',
    'swap', 'bridge', 'pledge', 'token_create',
    'nft_mint', 'nft_buy',
    'physical_asset_register', 'physical_asset_produce',
    'physical_asset_transfer',
})


def canonical_wallet_action_intent(intent: dict) -> str:
    fields = ('action', 'amount', 'asset', 'chain', 'created_at', 'from_thr',
              'nonce', 'payload_hash', 'recipient', 'type', 'version', 'wallet_id')
    parts = [f'"{k}":{json.dumps(str(intent.get(k, "")))}' for k in fields]
    return '{' + ','.join(parts) + '}'


def verify_action_payload_hash(expected_hash: str, payload: dict) -> bool:
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    actual = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return actual == expected_hash


def verify_wallet_action_signature(
    intent: dict,
    signature_hex: str,
    public_key_hex: str,
    max_age_seconds: int = 300,
) -> tuple:
    """Stateless verification of a signed wallet action intent (steps 1-5, 7, 8).

    Does NOT check or consume nonces — caller must handle replay protection.
    Returns (ok: bool, error_code: str, error_detail: str).
    """
    required = ('type', 'version', 'action', 'wallet_id', 'from_thr',
                'nonce', 'created_at', 'payload_hash')
    for field in required:
        if not intent.get(field):
            return False, 'missing_field', f'missing field: {field}'

    if intent.get('type') != 'thronos_wallet_action':
        return False, 'invalid_type', f'expected thronos_wallet_action, got {intent.get("type")!r}'

    if str(intent.get('version', '')) != '1':
        return False, 'invalid_version', f'expected version 1, got {intent.get("version")!r}'

    action = str(intent.get('action', ''))
    if action not in WALLET_ACTION_ALLOWED_ACTIONS:
        return False, 'invalid_action', f'action {action!r} not permitted'

    try:
        created_ts = int(str(intent.get('created_at', '0')))
        age = time.time() - created_ts
        if age < -30 or age > max_age_seconds:
            return False, 'intent_expired', f'intent age {int(age)}s exceeds {max_age_seconds}s window'
    except (ValueError, TypeError) as exc:
        return False, 'invalid_created_at', f'cannot parse created_at: {exc}'

    canonical_msg = canonical_wallet_action_intent(intent).encode('utf-8')
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.exceptions import InvalidSignature

        pub_bytes = bytes.fromhex(public_key_hex)
        sig_bytes = bytes.fromhex(signature_hex)
        pub_obj = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pub_bytes)
        pub_obj.verify(sig_bytes, canonical_msg, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False, 'invalid_signature', 'signature does not match intent'
    except Exception as exc:
        return False, 'invalid_signature', f'signature verification failed: {exc}'

    try:
        import wallet_v1_production_final as _wv1
        binding_ok, binding_error = _wv1.verify_publickey_matches_address(
            {'from': str(intent['from_thr']).upper(), 'publicKey': public_key_hex}
        )
        if not binding_ok:
            return False, 'key_address_mismatch', binding_error
    except Exception as exc:
        return False, 'key_address_mismatch', f'address binding failed: {exc}'

    return True, '', ''
