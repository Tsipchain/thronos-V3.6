from wallet_v1_migration import resolve_migration


class AdmissionError(Exception):
    pass


def _server():
    import server
    return server


def require_active_thr_address(address):
    if not address:
        raise AdmissionError('missing_address')

    rec = resolve_migration(address)
    if rec:
        status = rec.get('status')
        if address == rec.get('old_address') and status in ('completed', 'repaired'):
            raise AdmissionError('legacy_address_migrated_read_only')
        if address == rec.get('new_v1_address'):
            if status in ('completed', 'repaired'):
                return True
            raise AdmissionError('migration_not_completed')

    s = _server()
    resolver = getattr(s, 'resolve_wallet_pledge_state', None)
    if callable(resolver):
        st = resolver(address)
        if isinstance(st, dict) and (st.get('active') or st.get('pledged') or st.get('admitted')):
            return True

    if callable(getattr(s, 'has_pledge_access', None)) and s.has_pledge_access(address):
        return True
    if callable(getattr(s, 'is_wallet_whitelisted', None)) and s.is_wallet_whitelisted(address):
        return True

    get_mining = getattr(s, 'get_mining_whitelist_entry', None)
    allows = getattr(s, '_whitelist_allows_no_pledge', None)
    if callable(get_mining):
        entry = get_mining(address)
        if entry and entry.get('active', True) and not entry.get('banned', False):
            if entry.get('pledge_ok'):
                return True
            if callable(allows) and allows(entry):
                return True

    raise AdmissionError('inactive_thr_address')
