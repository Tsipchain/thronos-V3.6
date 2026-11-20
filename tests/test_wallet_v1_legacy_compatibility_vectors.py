import hashlib
from pathlib import Path

from wallet_v1_address_derivation import derive_thronos_address, validate_thronos_address


SYNTHETIC_PLEDGE_SECRET = "synthetic-wallet-pledge-secret-v1"
GENERATOR_COMPRESSED_PUBLIC_KEY = (
    "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
)


def test_pledge_credential_hash_golden_vectors_are_byte_exact():
    h1 = hashlib.sha256(SYNTHETIC_PLEDGE_SECRET.encode()).hexdigest()
    # Historical "SHA256d" label hashes the ASCII hex of h1.  It is not the
    # standard SHA256(SHA256(secret).digest()) formula and must never be changed.
    h2 = hashlib.sha256(h1.encode()).hexdigest()
    h3 = hashlib.sha256(f"{SYNTHETIC_PLEDGE_SECRET}:auth".encode()).hexdigest()

    assert h1 == "023bbaa348ab74d5a09628e2f4c98f34bb6829d24463c2f657f25406762f27a1"
    assert h2 == "79152e3a732365b7eb7508150f1bc200c4cd5ade32f8e1c2dfad0cdbe86ded93"
    assert h3 == "ab9553da6eff345f67ec63021048e8abf97f11ab2be2712950887012365fd103"
    assert h2 != hashlib.sha256(hashlib.sha256(SYNTHETIC_PLEDGE_SECRET.encode()).digest()).hexdigest()


def test_lookup_and_migrate_keep_all_three_historical_hash_variants():
    source = (Path(__file__).parents[1] / "server_ext.py").read_text()
    assert source.count("h1 = _hashlib.sha256(send_secret.encode()).hexdigest()") == 2
    assert source.count("h2 = _hashlib.sha256(h1.encode()).hexdigest()") == 2
    assert source.count("h3 = _hashlib.sha256(f'{send_secret}:auth'.encode()).hexdigest()") == 2
    assert source.count("stored in (h1, h2, h3)") == 2


def test_canonical_address_derivation_golden_vector_is_unchanged():
    address = derive_thronos_address(GENERATOR_COMPRESSED_PUBLIC_KEY)
    assert address == "THR751E76E8199196D454941C45D1B3A323F1433BD6"
    assert validate_thronos_address(address) is True


def test_verifier_change_does_not_edit_pledge_or_migration_algorithms():
    verifier = (Path(__file__).parents[1] / "wallet_v1_signed_request_verifier.py").read_text()
    assert "send_secret" not in verifier
    assert "migrate_legacy_address" not in verifier
    assert "PLEDGE_CHAIN" not in verifier
