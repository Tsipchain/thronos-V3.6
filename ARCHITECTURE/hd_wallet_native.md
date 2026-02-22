# Native HD Wallet Architecture (BIP39/BIP44)

## Overview
Implement native hierarchical deterministic (HD) wallet support in Thronos blockchain.
This enables:
- 12/24-word mnemonic seed phrases
- Deterministic address generation
- Multi-account support from single seed
- Hardware wallet compatibility
- Browser extension integration

---

## Standards Compliance

### BIP39 (Mnemonic Seed)
- **Entropy:** 128-256 bits
- **Mnemonic:** 12-24 words from standardized wordlist
- **Languages:** English (primary), support for others optional
- **Passphrase:** Optional BIP39 passphrase for additional security

### BIP44 (HD Derivation Path)
```
m / purpose' / coin_type' / account' / change / address_index

Thronos Path:
m / 44' / 1337' / 0' / 0 / 0  (first address, first account)
m / 44' / 1337' / 0' / 0 / 1  (second address, first account)
m / 44' / 1337' / 1' / 0 / 0  (first address, second account)
```

**Coin Type:** `1337` (Thronos custom, registered with SLIP-0044)

---

## Implementation Components

### 1. Core HD Wallet Module
**File:** `core/hd_wallet.py`

```python
import hashlib
import hmac
from mnemonic import Mnemonic
from bip32 import BIP32

class ThronosHDWallet:
    """Native BIP39/BIP44 HD wallet for Thronos blockchain."""
    
    COIN_TYPE = 1337  # Thronos coin type
    
    def __init__(self, mnemonic: str = None, passphrase: str = ""):
        """Initialize HD wallet from mnemonic or generate new one."""
        self.mnemonic_gen = Mnemonic("english")
        
        if mnemonic:
            if not self.mnemonic_gen.check(mnemonic):
                raise ValueError("Invalid mnemonic")
            self.mnemonic = mnemonic
        else:
            self.mnemonic = self.mnemonic_gen.generate(strength=256)  # 24 words
        
        # Generate seed from mnemonic + passphrase
        self.seed = self.mnemonic_gen.to_seed(self.mnemonic, passphrase)
        
        # Create BIP32 root key
        self.bip32 = BIP32.from_seed(self.seed)
    
    def derive_address(self, account: int = 0, index: int = 0) -> str:
        """Derive Thronos address at BIP44 path."""
        path = f"m/44'/{self.COIN_TYPE}'/{account}'/0/{index}"
        child_key = self.bip32.get_privkey_from_path(path)
        
        # Convert to Thronos address format
        return self._privkey_to_thronos_address(child_key)
    
    def derive_private_key(self, account: int = 0, index: int = 0) -> bytes:
        """Derive private key at BIP44 path."""
        path = f"m/44'/{self.COIN_TYPE}'/{account}'/0/{index}"
        return self.bip32.get_privkey_from_path(path)
    
    def _privkey_to_thronos_address(self, private_key: bytes) -> str:
        """Convert private key to Thronos address (THR...)."""
        # TODO: Implement Thronos-specific address derivation
        # For now, use hash-based approach
        pubkey_hash = hashlib.sha256(private_key).hexdigest()[:40]
        return f"THR{pubkey_hash}"
    
    def export_mnemonic(self) -> str:
        """Export mnemonic seed phrase (12-24 words)."""
        return self.mnemonic
    
    def export_xprv(self) -> str:
        """Export extended private key (for wallet imports)."""
        return self.bip32.get_xpriv_from_path(f"m/44'/{self.COIN_TYPE}'/0'")
    
    def export_xpub(self) -> str:
        """Export extended public key (for watch-only wallets)."""
        return self.bip32.get_xpub_from_path(f"m/44'/{self.COIN_TYPE}'/0'")
```

---

### 2. Wallet API Endpoints
**File:** `server.py` (add new routes)

```python
@app.post("/api/wallet/hd/create")
def create_hd_wallet(strength: int = 256):
    """Create new HD wallet with mnemonic."""
    wallet = ThronosHDWallet()
    return {
        "mnemonic": wallet.export_mnemonic(),
        "first_address": wallet.derive_address(0, 0),
        "xpub": wallet.export_xpub()
    }

@app.post("/api/wallet/hd/restore")
def restore_hd_wallet(mnemonic: str, passphrase: str = ""):
    """Restore HD wallet from mnemonic."""
    try:
        wallet = ThronosHDWallet(mnemonic, passphrase)
        return {
            "success": True,
            "addresses": [
                wallet.derive_address(0, i) for i in range(5)
            ]
        }
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/wallet/hd/derive/{account}/{index}")
def derive_hd_address(account: int, index: int):
    """Derive address at specific BIP44 path."""
    # TODO: Load wallet from user session
    wallet = ThronosHDWallet()  # Mock
    return {
        "address": wallet.derive_address(account, index),
        "path": f"m/44'/1337'/{account}'/0/{index}"
    }
```

---

### 3. Browser Extension Integration
**File:** `extensions/chrome/background.js`

```javascript
// HD Wallet Extension
class ThronosHDExtension {
    constructor() {
        this.wallet = null;
    }
    
    async createWallet() {
        const response = await fetch('https://thronoschain.org/api/wallet/hd/create', {
            method: 'POST'
        });
        const data = await response.json();
        
        // Store encrypted mnemonic in extension storage
        await chrome.storage.local.set({
            encrypted_mnemonic: this.encrypt(data.mnemonic),
            xpub: data.xpub
        });
        
        return data;
    }
    
    async deriveAddress(account, index) {
        const { encrypted_mnemonic } = await chrome.storage.local.get('encrypted_mnemonic');
        const mnemonic = this.decrypt(encrypted_mnemonic);
        
        // Derive locally without sending mnemonic to server
        const hdWallet = new HDWallet(mnemonic);
        return hdWallet.deriveAddress(account, index);
    }
}
```

---

### 4. Hardware Wallet Support

**Ledger Integration:**
```python
from ledgerblue.comm import getDongle

def sign_with_ledger(tx_data: dict, path: str = "m/44'/1337'/0'/0/0"):
    """Sign transaction with Ledger hardware wallet."""
    dongle = getDongle(True)
    # Send transaction to Ledger for signing
    # User confirms on device
    signature = dongle.exchange(tx_data)
    return signature
```

**Trezor Integration:**
```python
from trezorlib.client import TrezorClient

def sign_with_trezor(tx_data: dict, path: str = "m/44'/1337'/0'/0/0"):
    """Sign transaction with Trezor hardware wallet."""
    client = TrezorClient()
    signature = client.sign_tx(path, tx_data)
    return signature
```

---

## Security Considerations

### Mnemonic Storage
- **Never store mnemonic in plaintext**
- Encrypt with user password (AES-256-GCM)
- Consider hardware security module (HSM) for server wallets
- Warn users to backup mnemonic offline

### Derivation Best Practices
- Use hardened derivation for accounts (`'` notation)
- Non-hardened for addresses (allows xpub derivation)
- Gap limit: scan 20 addresses for balance before stopping

### Key Management
- Private keys should never leave client device
- Use message signing for authentication (not private key sharing)
- Implement wallet locking after inactivity

---

## Migration Path

### From Legacy Wallets
```python
def migrate_legacy_to_hd(legacy_address: str, legacy_privkey: str):
    """Migrate existing wallet to HD."""
    # 1. Create new HD wallet
    hd_wallet = ThronosHDWallet()
    
    # 2. Transfer balance from legacy to HD address
    # (user must sign migration transaction)
    
    # 3. Return new mnemonic for backup
    return hd_wallet.export_mnemonic()
```

---

## Testing

```python
import pytest

def test_hd_wallet_creation():
    wallet = ThronosHDWallet()
    assert len(wallet.mnemonic.split()) == 24
    assert wallet.derive_address(0, 0).startswith('THR')

def test_hd_wallet_restoration():
    mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    wallet = ThronosHDWallet(mnemonic)
    address1 = wallet.derive_address(0, 0)
    
    # Restore from same mnemonic
    wallet2 = ThronosHDWallet(mnemonic)
    address2 = wallet2.derive_address(0, 0)
    
    assert address1 == address2  # Deterministic!

def test_multiple_accounts():
    wallet = ThronosHDWallet()
    account0_addr = wallet.derive_address(0, 0)
    account1_addr = wallet.derive_address(1, 0)
    assert account0_addr != account1_addr
```

---
## Implementation Priority

1. 🔴 **Core HD Wallet Module** (2-3 days)
2. 🟠 **API Endpoints** (1 day)
3. 🟡 **Frontend Integration** (2 days)
4. 🔵 **Browser Extension** (1 week)
5. 🟣 **Hardware Wallet Support** (optional, 1 week)

---

## Dependencies

```bash
pip install mnemonic bip32 ecdsa
```

```javascript
// Frontend
npm install bip39 bip32 bitcoinjs-lib
```

---

## Next Steps

1. Implement `core/hd_wallet.py`
2. Add API endpoints to `server.py`
3. Update wallet widget to support HD
4. Build browser extension prototype
5. Test with hardware wallets (Ledger/Trezor)
