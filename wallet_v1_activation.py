from wallet_v1_migration import resolve_migration


class AdmissionError(Exception):
    pass


def require_active_thr_address(address):
    if not address:
        raise AdmissionError('missing_address')
    rec = resolve_migration(address)
    if rec and rec.get('old_address') == address and rec.get('status') in ('completed', 'repaired'):
        raise AdmissionError('legacy_address_migrated_read_only')
    return True
