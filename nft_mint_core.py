"""
nft_mint_core — canonical NFT minting logic for Thronos.

Single implementation used by both the Wallet V1 route (server.py) and
the Physical Assets service. All storage I/O is injected via callbacks.
"""

import time


def generate_nft_id() -> str:
    return f"NFT{int(time.time() * 1000)}"


def _ensure_chain_tx(
    nft_id, tx_id, nft, name, creator, mint_fee,
    load_chain_fn, save_chain_fn, update_last_block_fn, network_wallet,
):
    """Ensure exactly one chain tx exists for this NFT. Returns tx_id or None."""
    if not load_chain_fn or not save_chain_fn:
        return None

    if tx_id is None:
        timestamp = nft.get('created_at', time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()))
        tx_id = f"{nft_id}-{timestamp.replace(' ', '-')}"

    chain = load_chain_fn()
    for existing_tx in chain:
        if existing_tx.get('tx_id') == tx_id:
            return tx_id

    timestamp = nft.get('created_at', time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()))
    effective_fee = mint_fee if mint_fee is not None else 0
    tx = {
        'type': 'nft_mint',
        'category': 'nft_mint',
        'tx_id': tx_id,
        'from': creator,
        'to': network_wallet,
        'amount': effective_fee,
        'fee': effective_fee,
        'fee_burned': effective_fee,
        'symbol': 'THR',
        'token_symbol': 'THR',
        'asset_symbol': 'THR',
        'nft_id': nft_id,
        'nft_name': name,
        'timestamp': timestamp,
        'status': 'confirmed',
    }
    chain.append(tx)
    save_chain_fn(chain)
    if update_last_block_fn:
        update_last_block_fn(tx, is_block=False)

    return tx_id


def canonical_mint_nft(
    name,
    description,
    category,
    price,
    royalties,
    creator,
    image_url=None,
    for_sale=True,
    mint_fee=0,
    extra_fields=None,
    nft_id=None,
    tx_id=None,
    load_nft_registry_fn=None,
    save_nft_registry_fn=None,
    load_chain_fn=None,
    save_chain_fn=None,
    update_last_block_fn=None,
    network_wallet='THR_NETWORK_FEES_00001',
):
    """Mint an NFT: assign ID, persist to registry, optionally record chain tx.

    Returns dict: nft_id, nft, tx_id (None when no chain callbacks provided).

    Exactly-once with partial-failure recovery:
    - If NFT exists in registry but chain tx is missing, reconstructs
      the chain tx without creating a duplicate NFT.
    - If chain tx exists, it is never duplicated.
    - After any retry: exactly 1 NFT, exactly 1 chain tx, same IDs.
    """
    if not load_nft_registry_fn or not save_nft_registry_fn:
        raise ValueError('NFT registry callbacks required')

    if nft_id is None:
        nft_id = generate_nft_id()

    registry = load_nft_registry_fn()

    existing_nft = None
    for entry in registry.get('nfts', []):
        if entry.get('id') == nft_id:
            existing_nft = entry
            break

    if existing_nft is not None:
        result_tx_id = _ensure_chain_tx(
            nft_id, tx_id, existing_nft, name, creator,
            mint_fee if mint_fee is not None else 0,
            load_chain_fn, save_chain_fn, update_last_block_fn, network_wallet,
        )
        return {'nft_id': nft_id, 'nft': existing_nft, 'tx_id': result_tx_id}

    timestamp = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
    effective_fee = mint_fee if mint_fee is not None else 0

    nft = {
        'id': nft_id,
        'name': name,
        'description': description,
        'category': category,
        'price': price,
        'royalties': royalties,
        'creator': creator,
        'owner': creator,
        'image_url': image_url,
        'created_at': timestamp,
        'for_sale': for_sale,
        'mint_fee': effective_fee,
    }
    if extra_fields:
        nft.update(extra_fields)

    registry.setdefault('nfts', []).append(nft)
    save_nft_registry_fn(registry)

    result_tx_id = _ensure_chain_tx(
        nft_id, tx_id, nft, name, creator, effective_fee,
        load_chain_fn, save_chain_fn, update_last_block_fn, network_wallet,
    )

    return {'nft_id': nft_id, 'nft': nft, 'tx_id': result_tx_id}
