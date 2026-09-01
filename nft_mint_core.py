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
    load_nft_registry_fn=None,
    save_nft_registry_fn=None,
    load_chain_fn=None,
    save_chain_fn=None,
    update_last_block_fn=None,
    network_wallet='THR_NETWORK_FEES_00001',
):
    """Mint an NFT: assign ID, persist to registry, optionally record chain tx.

    Returns dict: nft_id, nft, tx_id (None when no chain callbacks provided).
    """
    if not load_nft_registry_fn or not save_nft_registry_fn:
        raise ValueError('NFT registry callbacks required')

    if nft_id is None:
        nft_id = generate_nft_id()

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

    registry = load_nft_registry_fn()
    registry.setdefault('nfts', []).append(nft)
    save_nft_registry_fn(registry)

    tx_id = None
    if load_chain_fn and save_chain_fn:
        chain = load_chain_fn()
        tx = {
            'type': 'nft_mint',
            'category': 'nft_mint',
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
        tx_id = f"{nft_id}-{timestamp.replace(' ', '-')}"

    return {'nft_id': nft_id, 'nft': nft, 'tx_id': tx_id}
