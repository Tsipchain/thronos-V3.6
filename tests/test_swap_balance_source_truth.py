"""Swap frontend guards for THR AMM spendable balances vs cross-chain balances.

The test does not manufacture spendable USDT from BSC deposits. The swap
contract must continue to validate confirmed funds and pool liquidity server-side.
"""
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "templates" / "swap.html"


def test_swap_does_not_seed_missing_assets_with_fake_zero_balance():
    source = PAGE.read_text()
    assert "SWAP_KNOWN_SYMBOLS.forEach(sym => { balances[sym] = 0; });" not in source
    assert "function swapSpendableBalance(symbol)" in source
    assert "return null;" in source
    assert "swapBalanceLoadOk = false;" in source
    assert "if (!res.ok) throw new Error('balance_http_' + res.status);" in source


def test_crosschain_usdt_is_not_implicitly_spendable():
    source = PAGE.read_text()
    assert "swapExternalUsdtBsc" in source
    assert "data.balances?.USDT_bsc" in source
    assert "not yet verified as THR AMM spendable USDT" in source
    assert "applySwapBalance('USDT', data.USDT ?? data.usdt, balances)" in source
    assert "swapTokenBalances.USDT = swapExternalUsdtBsc" not in source


def test_swap_checks_verified_input_balance_on_quote_and_execution():
    source = PAGE.read_text()
    assert "const spendableBalance = swapSpendableBalance(tokenIn);" in source
    assert source.count("spendableBalance === null || spendableBalance <") >= 2
    assert "const fromBalance = swapSpendableBalance(tokenIn);" in source
    assert "fromBalance !== null && fromBalance >= amount" in source
    assert "alert(swapBalanceProblem(tokenIn));" in source


def test_existing_wallet_signing_and_pool_quote_paths_remain():
    source = PAGE.read_text()
    assert "walletV1BuildSignedRequest(\"swap\", payload)" in source
    assert "fetch('/api/swap/execute'" in source
    assert "fetch('/api/v1/pools')" in source
    assert "fetch('/api/v1/tokens')" in source
    assert "fetch(`/api/swap/quote?" in source
    assert "SWAP_KNOWN_SYMBOLS = ['THR', 'USDT', 'USDC'," in source
