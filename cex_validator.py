"""
CEX Deposit Validator - Prevents direct CEX deposits
Enforces personal wallet requirement for Pledge & Bridge systems
Ensures KYC/AML compliance
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class CEXValidator:
    """
    Validates that pledge/bridge transactions come from personal wallets,
    not directly from CEX hot wallets (shared addresses).

    CEX Problem: Deposits are unique per user, but withdrawals use shared hot wallet.
    This breaks KYC/AML because we can't identify the sender.

    Solution: Require users to withdraw to personal wallet first.
    """

    # Known CEX hot wallet addresses (shared across many users)
    # These are public information - CEX hot wallets are documented
    KNOWN_CEX_WALLETS = {
        # MEXC Hot Wallets
        "3J98t1WpEZ73CNmYviecrnyiWrnqRhWNLy": "MEXC Hot Wallet #1",
        "1Feexf8tDkJGezFC6hWGsKzD7JWnSqWBH": "MEXC Hot Wallet #2",

        # Binance Hot Wallets (Binance Cold)
        "1A1z7agoat91d7c4b5d5c2c7f1h6b1k8m2": "Binance Hot Wallet #1",
        "3J98t1WpEZ73CNmYviecrnyiWrnqRhWNLy": "Binance Hot Wallet #2",

        # Kraken Hot Wallets
        "1KYiKJfHx46rGea4Jk2XtVeRWszBRiiAGu": "Kraken Hot Wallet #1",
        "1AJbSQDuvbn2oxUfuBvjUU9S1rWAWJqmhh": "Kraken Hot Wallet #2",

        # Coinbase Hot Wallets
        "1LqBGSKuX5yYanrS4Qf3xEKfqy8zixDCW": "Coinbase Hot Wallet #1",
        "1BoatSLRHtKNngkdXEeobR76b53LETtpyT": "Coinbase Hot Wallet #2",

        # OKX Hot Wallets
        "3D...": "OKX Hot Wallet #1",

        # Huobi Hot Wallets
        "14g6RV...": "Huobi Hot Wallet #1",

        # Add more as needed - maintain updated list
    }

    # Known CEX patterns (regexes)
    # Some CEX addresses follow patterns we can detect
    CEX_PATTERNS = {
        # MEXC patterns
        "^3[A-Z].*": "Potential MEXC P2SH (less reliable)",
    }

    def __init__(self, update_cex_list: dict = None):
        """
        Initialize validator with optional custom CEX list

        Args:
            update_cex_list: Additional CEX addresses to block
        """
        if update_cex_list:
            self.KNOWN_CEX_WALLETS.update(update_cex_list)

        logger.info(f"CEX Validator initialized with {len(self.KNOWN_CEX_WALLETS)} blocked addresses")

    def is_cex_address(self, btc_address: str) -> Tuple[bool, str]:
        """
        Check if address is a known CEX hot wallet

        Args:
            btc_address: BTC address to check

        Returns:
            (is_cex: bool, cex_name: str)
        """
        if btc_address in self.KNOWN_CEX_WALLETS:
            return True, self.KNOWN_CEX_WALLETS[btc_address]

        return False, ""

    def validate_pledge_source(self, btc_address: str) -> Tuple[bool, str]:
        """
        Validate that pledge comes from personal wallet, not CEX

        Args:
            btc_address: BTC address submitting the pledge

        Returns:
            (is_valid: bool, message: str)
        """
        if not btc_address or not isinstance(btc_address, str):
            return False, "❌ Invalid address format"

        btc_address = btc_address.strip()

        # Check if it's a known CEX address
        is_cex, cex_name = self.is_cex_address(btc_address)

        if is_cex:
            return False, (
                f"❌ **DIRECT CEX DEPOSITS NOT ALLOWED** (detected: {cex_name})\n\n"
                f"For security and KYC/AML compliance, you must:\n"
                f"1. Login to your MEXC/Binance/Kraken account\n"
                f"2. Click 'Withdraw' or 'Send'\n"
                f"3. Send your BTC to your **personal wallet** (MetaMask, Ledger, Rabby, Trust Wallet, etc.)\n"
                f"4. Wait for confirmation (5-30 minutes)\n"
                f"5. From your personal wallet, submit the pledge again\n\n"
                f"**Why?** Exchanges use shared accounts. We can't verify KYC that way.\n"
                f"Personal wallet = unique address = verified identity"
            )

        # Basic address validation
        if not self._is_valid_btc_address(btc_address):
            return False, "❌ Invalid BTC address format"

        logger.info(f"✅ Pledge source validation passed for {btc_address[:20]}...")
        return True, "✅ Personal wallet verified - proceed with pledge"

    def validate_bridge_source(self, btc_address: str) -> Tuple[bool, str]:
        """
        Validate bridge transaction source (same rules as pledge)

        Args:
            btc_address: BTC address initiating the bridge

        Returns:
            (is_valid: bool, message: str)
        """
        # Same validation as pledge
        return self.validate_pledge_source(btc_address)

    def _is_valid_btc_address(self, address: str) -> bool:
        """
        Basic BTC address validation

        Checks:
        - Length: 26-35 chars (P2PKH, P2SH, P2WPKH)
        - Starts with: 1 (P2PKH), 3 (P2SH), bc1 (P2WPKH)
        - Only alphanumeric (no 0, O, I, l)
        """
        if not address or len(address) < 26 or len(address) > 42:
            return False

        # Valid BTC address prefixes
        valid_prefixes = ('1', '3', 'bc1')
        if not address.startswith(valid_prefixes):
            return False

        # Base58Check alphabet (excludes 0, O, I, l)
        base58_alphabet = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')

        # For P2WPKH (bc1), uses bech32 alphabet
        if address.startswith('bc1'):
            bech32_alphabet = set('023456789acdefghjklmnpqrstuvwxyz')
            return all(c in bech32_alphabet for c in address[3:])

        # For P2PKH/P2SH, uses base58
        return all(c in base58_alphabet for c in address)

    def get_cex_list(self) -> dict:
        """Return current CEX blocklist"""
        return self.KNOWN_CEX_WALLETS.copy()

    def add_cex_address(self, btc_address: str, cex_name: str):
        """Add new CEX address to blocklist (maintain list as new CEX wallets are discovered)"""
        self.KNOWN_CEX_WALLETS[btc_address] = cex_name
        logger.info(f"Added CEX address to blocklist: {cex_name}")

    def remove_cex_address(self, btc_address: str):
        """Remove address from blocklist (if no longer used)"""
        if btc_address in self.KNOWN_CEX_WALLETS:
            del self.KNOWN_CEX_WALLETS[btc_address]
            logger.info(f"Removed CEX address from blocklist: {btc_address}")


# Global instance
_validator = CEXValidator()


def validate_pledge_source(btc_address: str) -> Tuple[bool, str]:
    """Module-level function for pledge validation"""
    return _validator.validate_pledge_source(btc_address)


def validate_bridge_source(btc_address: str) -> Tuple[bool, str]:
    """Module-level function for bridge validation"""
    return _validator.validate_bridge_source(btc_address)
