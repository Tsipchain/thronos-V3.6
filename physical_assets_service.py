"""
Physical Assets Registry — core service for Thronos Physical Assets.

Manages the lifecycle of physical assets (3D-printed coins, collectibles)
from registration through NFT minting, claim, and transfer.

Storage: JSON file in DATA_DIR (physical_assets_registry.json).
Concurrency: file-level locking via threading.Lock + atomic writes.
Serial format: {SKU}-{edition_number:03d}  e.g. TPC-S1-001
"""

import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ── Lifecycle states ─────────────────────────────────────────────────────────
ASSET_STATES = (
    'REGISTERED',
    'SERIAL_RESERVED',
    'PENDING_PRODUCTION',
    'PRODUCED',
    'MINT_PENDING',
    'MINTED',
    'CLAIM_PENDING',
    'CLAIMED',
    'TRANSFERRED',
    'RETIRED',
)

VALID_ASSET_TYPES = (
    'THR_BACKED_COLLECTIBLE',
    'COLLECTIBLE',
    'CERTIFICATE',
    'PROOF_OF_AUTHENTICITY',
)

VALID_CERTIFICATION_MODES = ('MANUAL', 'ON_PRODUCTION')
VALID_MINT_MODES = ('MANUAL', 'ON_PURCHASE', 'PRE_MINTED', 'ON_PRODUCTION')

# Serial format: alphanumeric + hyphens, 3-64 chars
_SERIAL_RE = re.compile(r'^[A-Z0-9][A-Z0-9\-]{1,62}[A-Z0-9]$')
_ID_RE = re.compile(r'^[a-f0-9]{32}$')

# ── Module state (injected at init) ──────────────────────────────────────────
_lock = threading.Lock()
_registry_file: Optional[str] = None
_load_json = None
_save_json = None
_node_role = 'master'
_read_only = False
_feature_enabled = False

# NFT engine callbacks (injected from server.py)
_load_nft_registry = None
_save_nft_registry = None
_nft_mint_fee = 1.0


def init_physical_assets(
    data_dir: str,
    load_json_fn,
    save_json_fn,
    node_role: str = 'master',
    read_only: bool = False,
    feature_enabled: bool = False,
    load_nft_registry_fn=None,
    save_nft_registry_fn=None,
    nft_mint_fee: float = 1.0,
):
    global _registry_file, _load_json, _save_json, _node_role, _read_only
    global _feature_enabled, _load_nft_registry, _save_nft_registry, _nft_mint_fee

    _registry_file = os.path.join(data_dir, 'physical_assets_registry.json')
    _load_json = load_json_fn
    _save_json = save_json_fn
    _node_role = node_role
    _read_only = read_only
    _feature_enabled = feature_enabled
    _load_nft_registry = load_nft_registry_fn
    _save_nft_registry = save_nft_registry_fn
    _nft_mint_fee = nft_mint_fee


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _generate_id() -> str:
    return uuid.uuid4().hex


def _check_writable() -> Optional[str]:
    if _read_only or _node_role != 'master':
        return 'read_only_replica'
    if not _feature_enabled:
        return 'physical_assets_disabled'
    return None


def _load_registry() -> Dict[str, Any]:
    if not _load_json or not _registry_file:
        return {'assets': {}, 'serials': {}, 'idempotency': {}}
    data = _load_json(_registry_file, {'assets': {}, 'serials': {}, 'idempotency': {}})
    data.setdefault('assets', {})
    data.setdefault('serials', {})
    data.setdefault('idempotency', {})
    return data


def _save_registry(registry: Dict[str, Any]):
    if _save_json and _registry_file:
        _save_json(_registry_file, registry)


def _validate_serial(serial: str) -> Optional[str]:
    if not serial or not isinstance(serial, str):
        return 'serial_required'
    serial = serial.upper().strip()
    if not _SERIAL_RE.match(serial):
        return 'invalid_serial_format'
    return None


def _validate_design_hash(design_hash: str) -> Optional[str]:
    if not design_hash or not isinstance(design_hash, str):
        return 'design_hash_required'
    design_hash = design_hash.strip().lower()
    if not re.match(r'^[a-f0-9]{64}$', design_hash):
        return 'invalid_design_hash_format'
    return None


def _hash_claim_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode('utf-8')).hexdigest()


# ── Public API functions ─────────────────────────────────────────────────────

def register_asset(
    tenant_id: str,
    product_id: str,
    sku: str,
    serial: str,
    edition_number: int,
    edition_size: int,
    creator_address: str,
    design_hash: str,
    asset_type: str = 'COLLECTIBLE',
    idempotency_key: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    if not tenant_id or not isinstance(tenant_id, str):
        return False, {'error': 'tenant_id_required'}
    if not product_id or not isinstance(product_id, str):
        return False, {'error': 'product_id_required'}
    if not sku or not isinstance(sku, str):
        return False, {'error': 'sku_required'}

    serial = (serial or '').upper().strip()
    serial_err = _validate_serial(serial)
    if serial_err:
        return False, {'error': serial_err}

    if not isinstance(edition_number, int) or edition_number < 1:
        return False, {'error': 'invalid_edition_number'}
    if not isinstance(edition_size, int) or edition_size < 1:
        return False, {'error': 'invalid_edition_size'}
    if edition_number > edition_size:
        return False, {'error': 'edition_overflow'}

    if not creator_address or not isinstance(creator_address, str):
        return False, {'error': 'creator_address_required'}
    creator_address = creator_address.strip().upper()
    if not creator_address.startswith('THR'):
        return False, {'error': 'invalid_creator_address'}

    hash_err = _validate_design_hash(design_hash)
    if hash_err:
        return False, {'error': hash_err}
    design_hash = design_hash.strip().lower()

    if asset_type not in VALID_ASSET_TYPES:
        return False, {'error': 'invalid_asset_type', 'valid': list(VALID_ASSET_TYPES)}

    with _lock:
        registry = _load_registry()

        # Idempotency check
        if idempotency_key:
            existing_id = registry['idempotency'].get(idempotency_key)
            if existing_id and existing_id in registry['assets']:
                return True, registry['assets'][existing_id]

        # Duplicate serial check
        if serial in registry['serials']:
            return False, {'error': 'duplicate_serial', 'serial': serial}

        # Duplicate edition check (same product, same edition number)
        for asset in registry['assets'].values():
            if (asset.get('product_id') == product_id and
                    asset.get('edition_number') == edition_number and
                    asset.get('tenant_id') == tenant_id):
                return False, {'error': 'duplicate_edition', 'edition_number': edition_number}

        asset_id = _generate_id()
        now = _now_iso()

        asset = {
            'id': asset_id,
            'tenant_id': tenant_id,
            'product_id': product_id,
            'sku': sku,
            'serial': serial,
            'edition_number': edition_number,
            'edition_size': edition_size,
            'creator_address': creator_address,
            'design_hash': design_hash,
            'asset_type': asset_type,
            'state': 'REGISTERED',
            'nft_id': None,
            'nft_tx_id': None,
            'commerce_proof_link': None,
            'claim_secret_hash': None,
            'owner_address': None,
            'metadata': metadata or {},
            'created_at': now,
            'updated_at': now,
            'version': 1,
        }

        registry['assets'][asset_id] = asset
        registry['serials'][serial] = asset_id
        if idempotency_key:
            registry['idempotency'][idempotency_key] = asset_id

        _save_registry(registry)

    return True, asset


def get_asset(asset_id: str) -> Optional[Dict[str, Any]]:
    if not asset_id or not isinstance(asset_id, str):
        return None
    registry = _load_registry()
    return registry['assets'].get(asset_id)


def get_asset_by_serial(serial: str) -> Optional[Dict[str, Any]]:
    if not serial or not isinstance(serial, str):
        return None
    serial = serial.upper().strip()
    registry = _load_registry()
    asset_id = registry['serials'].get(serial)
    if asset_id:
        return registry['assets'].get(asset_id)
    return None


def get_asset_proof(asset_id: str) -> Optional[Dict[str, Any]]:
    asset = get_asset(asset_id)
    if not asset:
        return None
    return {
        'id': asset['id'],
        'serial': asset['serial'],
        'edition_number': asset['edition_number'],
        'edition_size': asset['edition_size'],
        'creator_address': asset['creator_address'],
        'design_hash': asset['design_hash'],
        'asset_type': asset['asset_type'],
        'state': asset['state'],
        'nft_id': asset.get('nft_id'),
        'created_at': asset['created_at'],
    }


def mint_asset_nft(
    asset_id: str,
    from_address: str,
    verified: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    if not _load_nft_registry or not _save_nft_registry:
        return False, {'error': 'nft_engine_unavailable'}

    with _lock:
        registry = _load_registry()
        asset = registry['assets'].get(asset_id)
        if not asset:
            return False, {'error': 'asset_not_found'}

        if asset.get('nft_id'):
            return True, {'nft_id': asset['nft_id'], 'already_minted': True}

        if asset['state'] not in ('REGISTERED', 'SERIAL_RESERVED', 'PRODUCED', 'PENDING_PRODUCTION'):
            return False, {'error': 'invalid_state_for_mint', 'state': asset['state']}

        from_address = from_address.strip().upper()
        if from_address != asset['creator_address'] and not verified:
            return False, {'error': 'unauthorized_mint'}

        nft_id = f"NFT-PA-{int(time.time() * 1000)}"
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())

        nft = {
            'id': nft_id,
            'name': f"Thronos Physical Asset {asset['serial']}",
            'description': (
                f"Physical Asset #{asset['edition_number']}/{asset['edition_size']} "
                f"| Serial: {asset['serial']} | Design: {asset['design_hash'][:16]}..."
            ),
            'category': 'physical_asset',
            'price': 0,
            'royalties': 10,
            'creator': asset['creator_address'],
            'owner': asset['creator_address'],
            'image_url': None,
            'created_at': timestamp,
            'for_sale': False,
            'mint_fee': 0,
            'physical_asset_id': asset_id,
            'serial': asset['serial'],
            'edition_number': asset['edition_number'],
            'edition_size': asset['edition_size'],
            'design_hash': asset['design_hash'],
        }

        nft_registry = _load_nft_registry()
        nft_registry.setdefault('nfts', []).append(nft)
        _save_nft_registry(nft_registry)

        asset['nft_id'] = nft_id
        asset['state'] = 'MINTED'
        asset['updated_at'] = _now_iso()
        asset['version'] += 1
        _save_registry(registry)

    return True, {'nft_id': nft_id, 'nft': nft}


def set_claim_secret(asset_id: str, claim_secret: str) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    if not claim_secret or len(claim_secret) < 8:
        return False, {'error': 'claim_secret_too_short'}

    with _lock:
        registry = _load_registry()
        asset = registry['assets'].get(asset_id)
        if not asset:
            return False, {'error': 'asset_not_found'}

        asset['claim_secret_hash'] = _hash_claim_secret(claim_secret)
        asset['state'] = 'CLAIM_PENDING'
        asset['updated_at'] = _now_iso()
        asset['version'] += 1
        _save_registry(registry)

    return True, {'id': asset_id, 'state': 'CLAIM_PENDING'}


def claim_asset(
    asset_id: str,
    claim_secret: str,
    new_owner_address: str,
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    if not new_owner_address or not isinstance(new_owner_address, str):
        return False, {'error': 'new_owner_address_required'}
    new_owner_address = new_owner_address.strip().upper()
    if not new_owner_address.startswith('THR'):
        return False, {'error': 'invalid_owner_address'}

    with _lock:
        registry = _load_registry()
        asset = registry['assets'].get(asset_id)
        if not asset:
            return False, {'error': 'asset_not_found'}

        if asset['state'] != 'CLAIM_PENDING':
            return False, {'error': 'asset_not_claimable', 'state': asset['state']}

        stored_hash = asset.get('claim_secret_hash')
        if not stored_hash:
            return False, {'error': 'no_claim_secret_set'}

        if _hash_claim_secret(claim_secret) != stored_hash:
            return False, {'error': 'invalid_claim_secret'}

        old_owner = asset.get('owner_address') or asset['creator_address']
        asset['owner_address'] = new_owner_address
        asset['state'] = 'CLAIMED'
        asset['claim_secret_hash'] = None
        asset['updated_at'] = _now_iso()
        asset['version'] += 1

        # Transfer NFT ownership if minted
        if asset.get('nft_id') and _load_nft_registry and _save_nft_registry:
            nft_registry = _load_nft_registry()
            for nft in nft_registry.get('nfts', []):
                if nft.get('id') == asset['nft_id']:
                    nft['owner'] = new_owner_address
                    break
            _save_nft_registry(nft_registry)

        _save_registry(registry)

    return True, {'id': asset_id, 'state': 'CLAIMED', 'owner_address': new_owner_address}


def transfer_asset(
    asset_id: str,
    from_address: str,
    to_address: str,
    verified: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    if not to_address or not isinstance(to_address, str):
        return False, {'error': 'to_address_required'}
    to_address = to_address.strip().upper()
    if not to_address.startswith('THR'):
        return False, {'error': 'invalid_to_address'}

    from_address = (from_address or '').strip().upper()

    with _lock:
        registry = _load_registry()
        asset = registry['assets'].get(asset_id)
        if not asset:
            return False, {'error': 'asset_not_found'}

        if asset['state'] not in ('MINTED', 'CLAIMED', 'TRANSFERRED'):
            return False, {'error': 'invalid_state_for_transfer', 'state': asset['state']}

        current_owner = asset.get('owner_address') or asset['creator_address']
        if from_address != current_owner and not verified:
            return False, {'error': 'unauthorized_transfer'}

        asset['owner_address'] = to_address
        asset['state'] = 'TRANSFERRED'
        asset['updated_at'] = _now_iso()
        asset['version'] += 1

        # Transfer NFT ownership
        if asset.get('nft_id') and _load_nft_registry and _save_nft_registry:
            nft_registry = _load_nft_registry()
            for nft in nft_registry.get('nfts', []):
                if nft.get('id') == asset['nft_id']:
                    nft['owner'] = to_address
                    break
            _save_nft_registry(nft_registry)

        _save_registry(registry)

    return True, {'id': asset_id, 'state': 'TRANSFERRED', 'owner_address': to_address}


def list_assets(
    tenant_id: Optional[str] = None,
    product_id: Optional[str] = None,
    state: Optional[str] = None,
    creator_address: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    registry = _load_registry()
    assets = list(registry['assets'].values())

    if tenant_id:
        assets = [a for a in assets if a.get('tenant_id') == tenant_id]
    if product_id:
        assets = [a for a in assets if a.get('product_id') == product_id]
    if state:
        assets = [a for a in assets if a.get('state') == state]
    if creator_address:
        creator_address = creator_address.strip().upper()
        assets = [a for a in assets if a.get('creator_address') == creator_address]

    assets.sort(key=lambda a: a.get('created_at', ''), reverse=True)
    return assets[offset:offset + limit]


def update_asset_state(
    asset_id: str,
    new_state: str,
    updater_address: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    if new_state not in ASSET_STATES:
        return False, {'error': 'invalid_state', 'valid': list(ASSET_STATES)}

    with _lock:
        registry = _load_registry()
        asset = registry['assets'].get(asset_id)
        if not asset:
            return False, {'error': 'asset_not_found'}

        asset['state'] = new_state
        asset['updated_at'] = _now_iso()
        asset['version'] += 1
        _save_registry(registry)

    return True, asset
