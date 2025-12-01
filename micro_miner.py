"""
micro_miner.py
~~~~~~~~~~~~~~~

This script is a **proof‑of‑concept** micro miner for ThronosChain.  It
continuously hashes random nonces and prints the computed SHA‑256 digest.  In
real‑world mining, nodes compete to find a nonce that produces a block hash
below a network difficulty target.  Here we simply demonstrate the basic loop
without persisting any state or submitting results back to the network.

If you run this script, it will consume CPU cycles, so it is advisable to
adjust the loop count or add sleep calls as necessary for your environment.
"""

import hashlib
import os
import time


def mine(iterations: int = 100000) -> None:
    """Perform a fixed number of SHA‑256 hash computations.

    Parameters
    ----------
    iterations : int
        The number of random nonces to hash.  Increase this value to extend
        the mining loop.  In a real miner, this would run indefinitely.
    """
    for i in range(iterations):
        # Generate a random 32‑byte nonce
        nonce = os.urandom(32)
        # Compute SHA‑256 digest
        digest = hashlib.sha256(nonce).hexdigest()
        if i % 10000 == 0:
            print(f"[MicroMiner] iteration {i}, hash {digest[:16]}…")
    print("Micro miner completed", iterations, "iterations")


if __name__ == "__main__":
    # Run indefinitely in small batches
    try:
        while True:
            mine(100000)
            # Brief pause to allow interrupt handling
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Micro miner terminated by user")