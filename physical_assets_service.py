"""
Physical Assets Registry — core service for Thronos Physical Assets.

Manages the lifecycle of physical assets (3D-printed coins, collectibles)
from registration through NFT minting, claim, and transfer.

Storage: JSON file in DATA_DIR (physical_assets_registry.json).
Concurrency: file-level locking via threading.RLock + atomic writes.
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
_lock = threading.RLock()
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

# Canonical NFT mint adapter — injected at init, wraps nft_mint_core
_canonical_mint_fn = None


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
    canonical_mint_fn=None,
):
    global _registry_file, _load_json, _save_json, _node_role, _read_only
    global _feature_enabled, _load_nft_registry, _save_nft_registry, _nft_mint_fee
    global _canonical_mint_fn

    _registry_file = os.path.join(data_dir, 'physical_assets_registry.json')
    _load_json = load_json_fn
    _save_json = save_json_fn
    _node_role = node_role
    _read_only = read_only
    _feature_enabled = feature_enabled
    _load_nft_registry = load_nft_registry_fn
    _save_nft_registry = save_nft_registry_fn
    _nft_mint_fee = nft_mint_fee
    _canonical_mint_fn = canonical_mint_fn


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
    creation_fee: float = 0.0,
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
            'nft_mint_status': None,
            'commerce_proof_link': None,
            'claim_secret_hash': None,
            'owner_address': None,
            'creation_fee': max(0.0, float(creation_fee)),
            'listing_price': 0,
            'for_sale': False,
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

    if not _canonical_mint_fn:
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

        result = _canonical_mint_fn(
            name=f"Thronos Physical Asset {asset['serial']}",
            description=(
                f"Physical Asset #{asset['edition_number']}/{asset['edition_size']} "
                f"| Serial: {asset['serial']} | Design: {asset['design_hash'][:16]}..."
            ),
            category='physical_asset',
            price=asset.get('listing_price', 0),
            royalties=5,
            creator=asset['creator_address'],
            for_sale=asset.get('for_sale', False),
            mint_fee=0,
            extra_fields={
                'creation_fee': asset.get('creation_fee', 0),
                'physical_asset_id': asset_id,
                'serial': asset['serial'],
                'edition_number': asset['edition_number'],
                'edition_size': asset['edition_size'],
                'design_hash': asset['design_hash'],
            },
        )

        nft_id = result['nft_id']
        asset['nft_id'] = nft_id
        asset['nft_tx_id'] = result.get('tx_id')
        asset['nft_mint_status'] = 'confirmed'
        asset['state'] = 'MINTED'
        asset['updated_at'] = _now_iso()
        asset['version'] += 1
        _save_registry(registry)

    return True, {'nft_id': nft_id, 'nft': result.get('nft'), 'tx_id': result.get('tx_id')}


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


# ── Production layer (Stage 2) ──────────────────────────────────────────────
# Batches, jobs, design file hashing, creator-signed production attestation.
#
# Flow:  3MF upload → hash → register asset → serial assigned
#        → gcode uploaded+hashed → production job created → printer prints
#        → creator signs attestation → canonical NFT mint → CERTIFIED

BATCH_STATES = ('PLANNED', 'ACTIVE', 'COMPLETED', 'CANCELLED')

JOB_STATES = (
    'PLANNED',
    'GCODE_READY',
    'PRINTING',
    'PRINT_FAILED',
    'PRINTED',
    'CREATOR_SIGNED',
    'MINT_PENDING',
    'CHAIN_CONFIRMED',
    'NFT_CONFIRMED',
    'CERTIFIED',
    'AVAILABLE',
)

_APPROVED_CREATORS_FILE = 'approved_creators.json'
_BATCHES_FILE = 'production_batches.json'
_DESIGNS_DIR = 'designs'


def _batches_file() -> Optional[str]:
    if not _registry_file:
        return None
    return os.path.join(os.path.dirname(_registry_file), _BATCHES_FILE)


def _designs_dir() -> Optional[str]:
    if not _registry_file:
        return None
    d = os.path.join(os.path.dirname(_registry_file), _DESIGNS_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _approved_creators_file() -> Optional[str]:
    if not _registry_file:
        return None
    return os.path.join(os.path.dirname(_registry_file), _APPROVED_CREATORS_FILE)


def _load_batches() -> Dict[str, Any]:
    f = _batches_file()
    if not f or not _load_json:
        return {'batches': {}, 'jobs': {}}
    data = _load_json(f, {'batches': {}, 'jobs': {}})
    data.setdefault('batches', {})
    data.setdefault('jobs', {})
    return data


def _save_batches(data: Dict[str, Any]):
    f = _batches_file()
    if f and _save_json:
        _save_json(f, data)


def _load_approved_creators() -> Dict[str, Any]:
    f = _approved_creators_file()
    if not f or not _load_json:
        return {'creators': {}}
    data = _load_json(f, {'creators': {}})
    data.setdefault('creators', {})
    return data


def _save_approved_creators(data: Dict[str, Any]):
    f = _approved_creators_file()
    if f and _save_json:
        _save_json(f, data)


def is_approved_creator(
    creator_address: str,
    tenant_id: str,
    product_id: Optional[str] = None,
) -> bool:
    creators = _load_approved_creators()
    key = f"{tenant_id}:{creator_address.upper()}"
    entry = creators['creators'].get(key)
    if not entry or not entry.get('active'):
        return False
    allowed = entry.get('allowed_product_ids')
    if allowed and product_id and product_id not in allowed:
        return False
    return True


def approve_creator(
    tenant_id: str,
    creator_address: str,
    roles: Optional[List[str]] = None,
    allowed_product_ids: Optional[List[str]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    creator_address = creator_address.strip().upper()
    if not creator_address.startswith('THR'):
        return False, {'error': 'invalid_creator_address'}

    with _lock:
        creators = _load_approved_creators()
        key = f"{tenant_id}:{creator_address}"
        entry = {
            'tenant_id': tenant_id,
            'creator_address': creator_address,
            'roles': roles or ['creator', 'manufacturer'],
            'allowed_product_ids': allowed_product_ids,
            'active': True,
            'approved_at': _now_iso(),
        }
        creators['creators'][key] = entry
        _save_approved_creators(creators)

    return True, entry


def hash_design_file(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def hash_design_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_design_file(
    file_data: bytes,
    filename: str,
    tenant_id: str,
    product_id: str,
) -> Tuple[str, str]:
    d = _designs_dir()
    if not d:
        raise RuntimeError('designs directory unavailable')

    design_hash = hash_design_bytes(file_data)
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    stored_name = f"{tenant_id}_{product_id}_{design_hash[:16]}_{safe_name}"
    stored_path = os.path.join(d, stored_name)

    with open(stored_path, 'wb') as f:
        f.write(file_data)

    return design_hash, stored_path


def create_production_batch(
    batch_id: str,
    tenant_id: str,
    product_id: str,
    sku: str,
    creator_address: str,
    quantity: int,
    edition_start: int,
    edition_size: int,
    design_hash: str,
    design_format: str = '3mf',
    creation_fee: float = 0.0,
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    creator_address = creator_address.strip().upper()
    if not is_approved_creator(creator_address, tenant_id, product_id):
        return False, {'error': 'creator_not_approved'}

    if not isinstance(quantity, int) or quantity < 1:
        return False, {'error': 'invalid_quantity'}
    if not isinstance(edition_start, int) or edition_start < 1:
        return False, {'error': 'invalid_edition_start'}
    if edition_start + quantity - 1 > edition_size:
        return False, {'error': 'edition_overflow',
                       'detail': f'editions {edition_start}..{edition_start+quantity-1} exceed size {edition_size}'}

    hash_err = _validate_design_hash(design_hash)
    if hash_err:
        return False, {'error': hash_err}

    with _lock:
        batches_data = _load_batches()

        if batch_id in batches_data['batches']:
            existing = batches_data['batches'][batch_id]
            if existing.get('design_hash') == design_hash.lower():
                return True, existing
            return False, {'error': 'duplicate_batch_id'}

        now = _now_iso()
        batch = {
            'batch_id': batch_id,
            'tenant_id': tenant_id,
            'product_id': product_id,
            'sku': sku,
            'creator_address': creator_address,
            'quantity': quantity,
            'edition_start': edition_start,
            'edition_size': edition_size,
            'design_hash': design_hash.lower(),
            'design_format': design_format,
            'creation_fee': max(0.0, float(creation_fee)),
            'status': 'PLANNED',
            'created_at': now,
            'updated_at': now,
        }

        # Create production jobs and register assets for each edition
        jobs = []
        for i in range(quantity):
            edition_number = edition_start + i
            serial = f"{sku}-{edition_number:03d}"
            job_id = f"{batch_id}-J{edition_number:03d}"

            # Register the asset
            ok, asset_result = register_asset(
                tenant_id=tenant_id,
                product_id=product_id,
                sku=sku,
                serial=serial,
                edition_number=edition_number,
                edition_size=edition_size,
                creator_address=creator_address,
                design_hash=design_hash,
                asset_type='THR_BACKED_COLLECTIBLE',
                idempotency_key=f"batch:{batch_id}:ed:{edition_number}",
                creation_fee=creation_fee,
            )
            if not ok:
                return False, {
                    'error': 'asset_registration_failed',
                    'edition_number': edition_number,
                    'detail': asset_result.get('error'),
                }

            asset_id = asset_result['id']

            job = {
                'job_id': job_id,
                'batch_id': batch_id,
                'asset_id': asset_id,
                'serial': serial,
                'edition_number': edition_number,
                'printer_id': None,
                'design_hash': design_hash.lower(),
                'gcode_hash': None,
                'status': 'PLANNED',
                'started_at': None,
                'completed_at': None,
                'creator_signature': None,
                'creator_tx_ref': None,
                'nft_id': None,
                'created_at': now,
                'updated_at': now,
            }
            batches_data['jobs'][job_id] = job
            jobs.append(job)

        batch['status'] = 'ACTIVE'
        batches_data['batches'][batch_id] = batch
        _save_batches(batches_data)

    return True, {'batch': batch, 'jobs': jobs}


def get_batch(batch_id: str) -> Optional[Dict[str, Any]]:
    batches_data = _load_batches()
    return batches_data['batches'].get(batch_id)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    batches_data = _load_batches()
    return batches_data['jobs'].get(job_id)


def list_jobs(
    batch_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    batches_data = _load_batches()
    jobs = list(batches_data['jobs'].values())
    if batch_id:
        jobs = [j for j in jobs if j.get('batch_id') == batch_id]
    if status:
        jobs = [j for j in jobs if j.get('status') == status]
    jobs.sort(key=lambda j: j.get('edition_number', 0))
    return jobs


def upload_job_gcode(
    job_id: str,
    gcode_hash: str,
    creator_address: str,
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    hash_err = _validate_design_hash(gcode_hash)
    if hash_err:
        return False, {'error': 'invalid_gcode_hash'}

    with _lock:
        batches_data = _load_batches()
        job = batches_data['jobs'].get(job_id)
        if not job:
            return False, {'error': 'job_not_found'}

        batch = batches_data['batches'].get(job['batch_id'])
        if not batch:
            return False, {'error': 'batch_not_found'}

        creator_address = creator_address.strip().upper()
        if creator_address != batch['creator_address']:
            return False, {'error': 'unauthorized_creator'}

        job['gcode_hash'] = gcode_hash.lower()
        job['status'] = 'GCODE_READY'
        job['updated_at'] = _now_iso()
        _save_batches(batches_data)

    return True, job


def start_print_job(
    job_id: str,
    printer_id: str,
    creator_address: str,
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    with _lock:
        batches_data = _load_batches()
        job = batches_data['jobs'].get(job_id)
        if not job:
            return False, {'error': 'job_not_found'}

        batch = batches_data['batches'].get(job['batch_id'])
        if not batch:
            return False, {'error': 'batch_not_found'}

        creator_address = creator_address.strip().upper()
        if creator_address != batch['creator_address']:
            return False, {'error': 'unauthorized_creator'}

        if job['status'] not in ('PLANNED', 'GCODE_READY', 'PRINT_FAILED'):
            return False, {'error': 'invalid_job_state', 'state': job['status']}

        job['printer_id'] = printer_id
        job['status'] = 'PRINTING'
        job['started_at'] = _now_iso()
        job['updated_at'] = _now_iso()

        # Update the asset state
        registry = _load_registry()
        asset = registry['assets'].get(job['asset_id'])
        if asset:
            asset['state'] = 'PENDING_PRODUCTION'
            asset['updated_at'] = _now_iso()
            asset['version'] += 1
            _save_registry(registry)

        _save_batches(batches_data)

    return True, job


def fail_print_job(
    job_id: str,
    creator_address: str,
    reason: str = '',
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    with _lock:
        batches_data = _load_batches()
        job = batches_data['jobs'].get(job_id)
        if not job:
            return False, {'error': 'job_not_found'}

        batch = batches_data['batches'].get(job['batch_id'])
        if not batch:
            return False, {'error': 'batch_not_found'}

        creator_address = creator_address.strip().upper()
        if creator_address != batch['creator_address']:
            return False, {'error': 'unauthorized_creator'}

        if job['status'] != 'PRINTING':
            return False, {'error': 'job_not_printing', 'state': job['status']}

        job['status'] = 'PRINT_FAILED'
        job['updated_at'] = _now_iso()
        job['metadata'] = job.get('metadata', {})
        job['metadata']['fail_reason'] = reason
        _save_batches(batches_data)

    return True, job


def complete_print_job(
    job_id: str,
    creator_address: str,
) -> Tuple[bool, Dict[str, Any]]:
    err = _check_writable()
    if err:
        return False, {'error': err}

    with _lock:
        batches_data = _load_batches()
        job = batches_data['jobs'].get(job_id)
        if not job:
            return False, {'error': 'job_not_found'}

        batch = batches_data['batches'].get(job['batch_id'])
        if not batch:
            return False, {'error': 'batch_not_found'}

        creator_address = creator_address.strip().upper()
        if creator_address != batch['creator_address']:
            return False, {'error': 'unauthorized_creator'}

        if job['status'] != 'PRINTING':
            return False, {'error': 'job_not_printing', 'state': job['status']}

        job['status'] = 'PRINTED'
        job['completed_at'] = _now_iso()
        job['updated_at'] = _now_iso()

        registry = _load_registry()
        asset = registry['assets'].get(job['asset_id'])
        if asset:
            asset['state'] = 'PRODUCED'
            asset['updated_at'] = _now_iso()
            asset['version'] += 1
            _save_registry(registry)

        _save_batches(batches_data)

    return True, job


def sign_production(
    job_id: str,
    creator_address: str,
    signature_data: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    """Creator signs production attestation after successful print.

    Transitions to CREATOR_SIGNED. Does NOT mint NFT or certify — use
    certify_production() after signing to trigger canonical NFT mint.
    """
    err = _check_writable()
    if err:
        return False, {'error': err}

    with _lock:
        batches_data = _load_batches()
        job = batches_data['jobs'].get(job_id)
        if not job:
            return False, {'error': 'job_not_found'}

        batch = batches_data['batches'].get(job['batch_id'])
        if not batch:
            return False, {'error': 'batch_not_found'}

        creator_address = creator_address.strip().upper()
        if creator_address != batch['creator_address']:
            return False, {'error': 'unauthorized_creator'}

        if job['status'] == 'CERTIFIED':
            return True, {'job': job, 'already_certified': True}

        if job['status'] == 'CREATOR_SIGNED':
            return True, {'job': job, 'already_signed': True}

        if job['status'] != 'PRINTED':
            return False, {'error': 'job_not_printed', 'state': job['status']}

        # Verify signature binds the correct data
        required_bindings = [
            'tenant_id', 'batch_id', 'job_id', 'asset_id',
            'serial', 'edition_number', 'creator_address',
            'design_hash', 'nonce',
        ]
        for field in required_bindings:
            if not signature_data.get(field):
                return False, {'error': 'incomplete_signature', 'missing': field}

        if str(signature_data.get('design_hash', '')).lower() != job['design_hash']:
            return False, {'error': 'design_hash_mismatch'}

        if signature_data.get('serial') != job['serial']:
            return False, {'error': 'serial_mismatch'}

        if int(signature_data.get('edition_number', 0)) != job['edition_number']:
            return False, {'error': 'edition_mismatch'}

        job['creator_signature'] = signature_data.get('signature', '')
        job['status'] = 'CREATOR_SIGNED'
        job['updated_at'] = _now_iso()
        _save_batches(batches_data)

    return True, {'job': job, 'signed': True}


def certify_production(
    job_id: str,
    creator_address: str,
) -> Tuple[bool, Dict[str, Any]]:
    """Trigger canonical NFT mint after creator signing.

    CREATOR_SIGNED → MINT_PENDING → canonical mint → CERTIFIED.
    On mint failure, job stays MINT_PENDING (retryable).
    """
    err = _check_writable()
    if err:
        return False, {'error': err}

    with _lock:
        batches_data = _load_batches()
        job = batches_data['jobs'].get(job_id)
        if not job:
            return False, {'error': 'job_not_found'}

        batch = batches_data['batches'].get(job['batch_id'])
        if not batch:
            return False, {'error': 'batch_not_found'}

        creator_address = creator_address.strip().upper()
        if creator_address != batch['creator_address']:
            return False, {'error': 'unauthorized_creator'}

        if job['status'] == 'CERTIFIED':
            return True, {'job': job, 'already_certified': True, 'nft_id': job.get('nft_id')}

        if job['status'] not in ('CREATOR_SIGNED', 'MINT_PENDING'):
            return False, {'error': 'job_not_signed', 'state': job['status']}

        # Transition to MINT_PENDING before calling canonical mint
        job['status'] = 'MINT_PENDING'
        job['updated_at'] = _now_iso()
        _save_batches(batches_data)

    # Mint outside the lock (mint_asset_nft has its own lock)
    mint_ok, mint_result = mint_asset_nft(
        asset_id=job['asset_id'],
        from_address=creator_address,
        verified=True,
    )

    if not mint_ok:
        return False, {'error': 'nft_mint_failed', 'detail': mint_result.get('error'),
                       'retryable': True}

    with _lock:
        batches_data = _load_batches()
        job = batches_data['jobs'].get(job_id)
        if not job:
            return False, {'error': 'job_not_found'}

        job['nft_id'] = mint_result.get('nft_id')
        job['status'] = 'CERTIFIED'
        job['updated_at'] = _now_iso()

        # Check if all jobs in batch are certified
        all_batch_jobs = [j for j in batches_data['jobs'].values()
                         if j.get('batch_id') == job['batch_id']]
        if all(j.get('status') == 'CERTIFIED' for j in all_batch_jobs):
            batch = batches_data['batches'].get(job['batch_id'])
            if batch:
                batch['status'] = 'COMPLETED'
                batch['updated_at'] = _now_iso()

        _save_batches(batches_data)

    return True, {
        'job': job,
        'nft_id': mint_result.get('nft_id'),
        'tx_id': mint_result.get('tx_id'),
        'certified': True,
    }


def get_production_status(job_id: str) -> Optional[Dict[str, Any]]:
    batches_data = _load_batches()
    job = batches_data['jobs'].get(job_id)
    if not job:
        return None
    asset = get_asset(job.get('asset_id', ''))
    return {
        'job': job,
        'asset': asset,
        'batch_id': job.get('batch_id'),
    }
