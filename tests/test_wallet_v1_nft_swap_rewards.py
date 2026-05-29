from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_nft_buy_no_seed_prompt_and_uses_wallet_auth():
    text = (ROOT / "templates" / "nft.html").read_text(encoding="utf-8")
    assert "Εισάγετε το seed" not in text
    assert "seed σας" not in text
    assert "Enter your send seed" not in text
    assert "buyAuthSecret" not in text
    assert "WalletAuth.requireUnlockedWallet()" in text
    assert "async function requireNftWalletAuth" in text
    assert "fetch('/api/nfts/buy'" in text
    for field in ["buyer_thr", "credential_lookup_address", "public_key", "signed_tx", "signature"]:
        assert field in text


def test_nft_buy_route_exists():
    text = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '@app.route("/api/nfts/buy", methods=["POST"])' in text
    assert "verify_signed_transaction_core" in text


def test_no_plaintext_auth_secret_persistence_in_static_auth():
    combined = "\n".join((ROOT / p).read_text(encoding="utf-8") for p in [
        "static/wallet_auth.js",
        "public/static/wallet_auth.js",
        "templates/nft.html",
    ])
    assert "sessionStorage.setItem('thr_auth_secret'" not in combined
    assert 'sessionStorage.setItem("thr_auth_secret"' not in combined


def test_swap_quote_custom_token_no_route_is_clean(monkeypatch):
    import server
    monkeypatch.setattr(server, "get_all_tokens", lambda: [
        {"symbol": "THR"}, {"symbol": "7CEB"}, {"symbol": "HPENNIS"}
    ])
    monkeypatch.setattr(server, "load_pools", lambda: [])
    res = server.app.test_client().get('/api/swap/quote?token_in=7CEB&token_out=HPENNIS&amount_in=10')
    assert res.status_code in (400, 404)
    body = res.get_json()
    assert body["ok"] is False
    assert body["error"] == "no_swap_route"


def test_swap_quote_custom_token_direct_pool(monkeypatch):
    import server
    monkeypatch.setattr(server, "get_all_tokens", lambda: [
        {"symbol": "THR"}, {"symbol": "7CEB"}, {"symbol": "HPENNIS"}
    ])
    monkeypatch.setattr(server, "load_pools", lambda: [{
        "id": "p1", "token_a": "7CEB", "token_b": "HPENNIS", "reserves_a": 1000, "reserves_b": 500, "fee_bps": 30
    }])
    res = server.app.test_client().get('/api/swap/quote?token_in=7CEB&token_out=HPENNIS&amount_in=10')
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "success"
    assert body["route"] == ["7CEB", "HPENNIS"]
    assert body["amount_out"] > 0


def test_reward_diagnostics_endpoint_returns_json(monkeypatch):
    import server
    monkeypatch.setattr(server, "load_json", lambda path, default=None: {"THR" + "A" * 40: 6.4001} if path == server.LEDGER_FILE else (default if default is not None else []))
    monkeypatch.setattr(server, "_tx_feed", lambda **_kwargs: [])
    res = server.app.test_client().get('/api/v1/wallet/rewards/diagnostics?address=' + 'THR' + 'A' * 40)
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert "confirmed_thr_balance" in body
    assert "mining_rewards_confirmed" in body
    assert "pool_rewards_pending" in body
    assert "reward_wallet_bindings" in body


def test_swap_quote_custom_token_routed_through_thr(monkeypatch):
    import server
    monkeypatch.setattr(server, "get_all_tokens", lambda: [
        {"symbol": "THR"}, {"symbol": "7CEB"}, {"symbol": "HPENNIS"}
    ])
    monkeypatch.setattr(server, "load_pools", lambda: [
        {"id": "p1", "token_a": "7CEB", "token_b": "THR", "reserves_a": 1000, "reserves_b": 100, "fee_bps": 30},
        {"id": "p2", "token_a": "THR", "token_b": "HPENNIS", "reserves_a": 100, "reserves_b": 500, "fee_bps": 30},
    ])
    res = server.app.test_client().get('/api/swap/quote?token_in=7CEB&token_out=HPENNIS&amount_in=10')
    assert res.status_code == 200
    body = res.get_json()
    assert body["route"] == ["7CEB", "THR", "HPENNIS"]
    assert len(body["legs"]) == 2
    assert body["amount_out"] > 0


def test_reward_diagnostics_include_migration_binding(monkeypatch):
    import server
    old_addr = "THR" + "1" * 40
    new_addr = "THR" + "2" * 40
    monkeypatch.setattr(server, "load_json", lambda path, default=None: {new_addr: 6.4001} if path == server.LEDGER_FILE else (default if default is not None else []))
    monkeypatch.setattr(server, "_tx_feed", lambda **_kwargs: [
        {"type": "mining_reward", "to": old_addr, "amount": 1.25, "status": "pending", "miner": old_addr},
        {"type": "pool_reward", "wallet": new_addr, "amount": 0.5, "status": "confirmed"},
    ])
    import wallet_v1_migration
    monkeypatch.setattr(wallet_v1_migration, "_load_map", lambda: {old_addr: {"new_v1_address": new_addr, "status": "repaired"}})
    res = server.app.test_client().get('/api/v1/wallet/rewards/diagnostics?address=' + new_addr)
    assert res.status_code == 200
    body = res.get_json()
    assert old_addr in body["related_addresses"]
    assert body["mining_rewards_pending"] == 1.25
    assert body["pool_rewards_confirmed"] == 0.5
    assert body["reward_wallet_bindings"] == [{"old_address": old_addr, "new_v1_address": new_addr, "status": "repaired"}]
