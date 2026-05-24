from wallet_v1_migration import resolve_migration


class AdmissionError(Exception):
    pass


def _server():
    import server
    return server


def _migration_gate(address):
    rec = resolve_migration(address)
    if not rec:
        return None
    status = rec.get('status')
    old_addr = rec.get('old_address')
    new_addr = rec.get('new_v1_address')

    if address == old_addr:
        # old becomes read-only only after final statuses
        if status in ('completed', 'repaired'):
            raise AdmissionError('legacy_address_migrated_read_only')
        return None

    if address == new_addr:
        # new admitted only after final statuses
        if status in ('completed', 'repaired'):
            return True
        raise AdmissionError('migration_not_completed')

    return None


def _hook_true(name, address):
    s = _server()
    fn = getattr(s, name, None)
    if callable(fn):
        try:
            return bool(fn(address))
        except Exception:
            return False
    return False


def require_active_thr_address(address):
    if not address:
        raise AdmissionError('missing_address')

    mg = _migration_gate(address)
    if mg is True:
        return True

    # Preserve existing pledge/whitelist admission policies (best-effort hook set)
    s = _server()
    resolver = getattr(s, 'resolve_wallet_pledge_state', None)
    if callable(resolver):
        try:
            state = resolver(address)
            if isinstance(state, dict) and bool(state.get('active') or state.get('pledged') or state.get('admitted')):
                return True
            if isinstance(state, str) and state.lower() in ('active', 'pledged', 'admitted', 'approved', 'whitelisted'):
                return True
        except Exception:
            pass

    if _hook_true('has_pledge_access', address):
        return True
    if _hook_true('is_wallet_whitelisted', address):
        return True
    if _hook_true('is_whitelisted_address', address):
        return True
    if _hook_true('is_mining_whitelisted', address):
        return True
    if _hook_true('is_legacy_whitelisted', address):
        return True

    raise AdmissionError('inactive_thr_address')
