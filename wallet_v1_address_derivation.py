"""
Canonical Thronos Address Derivation Algorithm

All clients and backend MUST use this exact algorithm.

Standard: Bitcoin-style address derivation
1. Input: Compressed secp256k1 public key (hex string, 66 chars)
2. SHA256 hash of public key
3. RIPEMD160 hash of SHA256 result
4. Take first 40 characters (20 bytes) of RIPEMD160
5. Convert to uppercase
6. Prepend "THR"
7. Result: "THR" + 40 uppercase hex chars = 43-char address

Example:
  Input pubKey:    04e87c7fb40f8b99e49a41f50f81aeedc3b11f3fe60c4c0c8b63fa4c8e8b8e8b...
  SHA256:          8a9b8094faef738c4a7a794b07fb17328d8884fe7e5445e050c719c7ba42f4ca
  RIPEMD160:       3a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b
  First 40 chars:  3A7B8C9D0E1F2A3B4C5D6E7F8A9B0C1D2E3F4A5B (uppercase)
  Final address:   THR3A7B8C9D0E1F2A3B4C5D6E7F8A9B0C1D2E3F4A5B

This is the ONLY address derivation algorithm that must be used.
"""

import hashlib
import binascii


def derive_thronos_address(public_key_hex: str) -> str:
    """
    Derive Thronos address from compressed secp256k1 public key.
    
    Args:
        public_key_hex: Compressed public key as hex string (66 chars, starting with 02 or 03)
    
    Returns:
        Thronos address: "THR" + 40 uppercase hex chars (43 total)
    
    Raises:
        ValueError: If public key format is invalid
    """
    try:
        # Validate input
        if not isinstance(public_key_hex, str):
            raise ValueError("Public key must be hex string")
        
        if len(public_key_hex) != 66:
            raise ValueError(f"Compressed public key must be 66 chars, got {len(public_key_hex)}")
        
        if not public_key_hex.startswith(('02', '03')):
            raise ValueError(f"Compressed public key must start with 02 or 03, got {public_key_hex[:2]}")
        
        # Step 1: SHA256 of public key
        public_key_bytes = bytes.fromhex(public_key_hex)
        sha256_hash = hashlib.sha256(public_key_bytes).digest()
        
        # Step 2: RIPEMD160 of SHA256
        # Note: hashlib doesn't have ripemd160 in all Python versions
        # Using hashlib with 'ripemd160' algorithm (available in OpenSSL)
        try:
            ripemd160 = hashlib.new('ripemd160')
            ripemd160.update(sha256_hash)
            ripemd160_hash = ripemd160.digest()
        except ValueError:
            # Fallback: manually implement RIPEMD160 or use external library
            raise ValueError("RIPEMD160 not available in this Python installation")
        
        # Step 3: Take first 40 chars (20 bytes in hex = 40 chars)
        ripemd160_hex = ripemd160_hash.hex().upper()
        address_hash = ripemd160_hex[:40]
        
        # Step 4: Prepend "THR"
        address = f"THR{address_hash}"
        
        return address
    
    except Exception as e:
        raise ValueError(f"Failed to derive Thronos address: {e}")


def validate_thronos_address(address: str) -> bool:
    """
    Validate Thronos address format.
    
    Args:
        address: Address string to validate
    
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(address, str):
        return False
    
    if not address.startswith('THR'):
        return False
    
    if len(address) != 43:
        return False
    
    # Check if rest is valid hex (uppercase)
    try:
        int(address[3:], 16)
        return address[3:] == address[3:].upper()
    except ValueError:
        return False


if __name__ == '__main__':
    # Test cases
    print("Thronos Address Derivation Tests")
    print("=" * 70)
    
    # Test 1: Validation
    test_addresses = [
        ('THR3A7B8C9D0E1F2A3B4C5D6E7F8A9B0C1D2E3F4A5B', True),
        ('thr3a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b', False),  # lowercase
        ('THR3A7B8C9D0E1F2A3B4C5D6E7F8A9B0C1D2E3F4A', False),   # too short
        ('THR3A7B8C9D0E1F2A3B4C5D6E7F8A9B0C1D2E3F4A5BX', False), # too long
    ]
    
    for addr, expected in test_addresses:
        result = validate_thronos_address(addr)
        status = "✓" if result == expected else "✗"
        print(f"{status} Address: {addr} → {result} (expected {expected})")
    
    print("\n" + "=" * 70)
    print("CANONICAL ADDRESS DERIVATION SPEC DOCUMENTED")
    print("=" * 70)
