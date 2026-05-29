from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWAP = ROOT / "templates" / "swap.html"


def _swap() -> str:
    return SWAP.read_text(encoding="utf-8")


def test_swap_uses_active_wallet_auth_for_execute():
    text = _swap()
    assert "function getSwapActiveWalletAddress()" in text
    assert "window.getActiveWalletAddress" in text
    assert "async function requireSwapWalletAuth(txCore)" in text
    assert "WalletAuth.requireUnlockedWallet()" in text
    assert "walletSession.getSendSeed()" not in text
    assert "walletSession.requirePin('swap')" not in text


def test_swap_balance_parser_handles_known_api_shapes_and_symbols():
    text = _swap()
    for shape in ["data.tokens", "data.balances", "data.token_balances", "data.tokens_by_symbol"]:
        assert shape in text
    for symbol in ["THR", "WBTC", "L2E", "JAM", "LOUMIDIS", "HPENNIS", "CVT", "7CEB", "MAR"]:
        assert symbol in text
    for native_field in ["data.balance", "data.thr_balance", "data.wbtc_balance", "data.l2e_balance"]:
        assert native_field in text


def test_swap_sends_v1_signed_auth_fields():
    text = _swap()
    for field in [
        "trader_thr",
        "credential_lookup_address",
        "public_key",
        "signed_tx",
        "signature",
        "auth_secret",
    ]:
        assert field in text


def test_swap_normalize_signed_transaction_result_to_string_signature():
    text = _swap()
    assert "const signedTx = await wallet.signTransaction(txCore);" in text
    assert "const signature = typeof signedTx === 'string' ? signedTx : signedTx && signedTx.signature;" in text
    assert "signed_tx: typeof signedTx === 'string' ? { ...txCore, public_key: publicKey, signature } : signedTx" in text
