"""
nft_mint_core — canonical NFT minting logic for Thronos.

Single implementation used by both the Wallet V1 route (server.py) and
the Physical Assets service. All storage I/O is injected via callbacks.
"""

import time


def generate_nft_id() -> str:
    return f"NFT{int(time.time() * 1000)}"


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

    When nft_id is supplied, the mint is idempotent: if the registry
    already contains an NFT with that id, the existing record is returned
    without writing again.  Similarly, a supplied tx_id that already
    appears in the chain is not duplicated.
    """
    if not load_nft_registry_fn or not save_nft_registry_fn:
        raise ValueError('NFT registry callbacks required')

    if nft_id is None:
        nft_id = generate_nft_id()

    registry = load_nft_registry_fn()

    for existing in registry.get('nfts', []):
        if existing.get('id') == nft_id:
            existing_tx_id = None
            if load_chain_fn:
                for entry in load_chain_fn():
                    if entry.get('nft_id') == nft_id:
                        existing_tx_id = entry.get('tx_id')
                        break
            return {'nft_id': nft_id, 'nft': existing, 'tx_id': existing_tx_id}

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

    result_tx_id = None
    if load_chain_fn and save_chain_fn:
        if tx_id is None:
            tx_id = f"{nft_id}-{timestamp.replace(' ', '-')}"
        result_tx_id = tx_id

        chain = load_chain_fn()
        for existing_tx in chain:
            if existing_tx.get('tx_id') == tx_id:
                return {'nft_id': nft_id, 'nft': nft, 'tx_id': tx_id}

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

    return {'nft_id': nft_id, 'nft': nft, 'tx_id': result_tx_id}
