"""
wallet_crypto.py
~~~~~~~~~~~~~~~~~

This module contains a very simple cryptographic wallet implementation for
ThronosChain.  The production version of the network would normally rely on
robust elliptic‑curve cryptography (such as secp256k1) and base58 or bech32
address encoding.  However, the environment in which this example runs does not
ship with third‑party cryptographic libraries.  To keep the demonstration
self‑contained, this module uses Python's built‑in `os.urandom` to create a
random 256‑bit private key.  A corresponding "public key" is derived by
hashing the private key with SHA‑256.  The resulting Thronos address is
prefixed with ``THR`` and consists of the uppercase hexadecimal encoding of
the SHA‑256 hash of the public key.

This simplified scheme **does not provide true security**.  It serves only as
an illustration of how wallet addresses could be generated.  For a production
deployment you should integrate a proper ECDSA implementation and adhere
strictly to best practices around key generation and storage.
"""

import os
import hashlib
from dataclasses import dataclass


@dataclass
class WalletKey:
    """Container for a generated wallet key pair and address."""

    private_key: str
    public_key: str
    address: str


def generate_wallet() -> WalletKey:
    """Generate a new private/public key pair and Thronos address.

    Returns
    -------
    WalletKey
        A dataclass instance containing hexadecimal representations of the
        private key, public key and derived Thronos address.
    """
    # Generate a 256‑bit random private key
    priv = os.urandom(32)
    # Derive a "public key" by hashing the private key
    pub = hashlib.sha256(priv).digest()
    # Derive address by hashing the public key and prefixing with 'THR'
    addr_hash = hashlib.sha256(pub).hexdigest().upper()
    address = f"THR{addr_hash}"
    return WalletKey(
        private_key=priv.hex(),
        public_key=pub.hex(),
        address=address,
    )


def main() -> None:
    wallet = generate_wallet()
    print("Address :", wallet.address)
    print("Public  :", wallet.public_key)
    print("Private :", wallet.private_key)


if __name__ == "__main__":
    main()