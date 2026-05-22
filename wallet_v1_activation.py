"""Wallet V1 activation/admission checks for write authorization."""

import server as server_module


class AdmissionError(Exception):
    """Raised when a THR address is not admitted for Wallet V1 writes."""



def require_active_thr_address(address: str):
    """Require address to have network admission (pledge/whitelist/legacy policy)."""
    thr_address = (address or "").strip()
    if not thr_address:
        raise AdmissionError("missing_from_address")

    resolve_state = getattr(server_module, "resolve_wallet_pledge_state", None)
    if callable(resolve_state):
        state = resolve_state(thr_address)
        if isinstance(state, dict) and state.get("effective_pledge_ok"):
            return state

    has_pledge_access = getattr(server_module, "has_pledge_access", None)
    if callable(has_pledge_access) and has_pledge_access(thr_address):
        return {"effective_pledge_ok": True, "pledge_mode": "pledge_or_whitelist"}

    is_wallet_whitelisted = getattr(server_module, "is_wallet_whitelisted", None)
    if callable(is_wallet_whitelisted) and is_wallet_whitelisted(thr_address):
        return {"effective_pledge_ok": True, "pledge_mode": "whitelist"}

    get_mining_whitelist_entry = getattr(server_module, "get_mining_whitelist_entry", None)
    whitelist_allows = getattr(server_module, "_whitelist_allows_no_pledge", None)
    if callable(get_mining_whitelist_entry):
        entry = get_mining_whitelist_entry(thr_address)
        if isinstance(entry, dict) and entry.get("active", True) and not entry.get("banned", False):
            if callable(whitelist_allows) and whitelist_allows(entry):
                return {"effective_pledge_ok": True, "pledge_mode": "legacy_whitelist"}

    raise AdmissionError("inactive_thr_address")
