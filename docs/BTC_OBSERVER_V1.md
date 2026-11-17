# Bitcoin Observer v1 — Foundation

## Purpose

Provide one canonical, read-only Bitcoin deposit state layer for Bridge, Earn BTC accounting, and later Quantum Sentinel telemetry.

This foundation does **not** discover transactions, derive keys, sign, broadcast, mint, burn, or credit balances. A future local adapter (preferably ZMQ + private bitcoind RPC) supplies txids; the observer verifies the transaction through Bitcoin Core and persists matching outputs.

## Durable identity

Every observed deposit is keyed by:

`txid:vout`

Never by txid alone and never by an inferred sender address. A single Bitcoin transaction can pay the same watched address more than once and can have multiple unrelated inputs.

## State machine

`seen -> confirming -> confirmed -> credited`

A loss of finality or block-hash change after finality moves the event to:

`reorged`

`credited` is an explicit bookkeeping mark only. This module never performs the corresponding THR/THC/WBTC credit. A reorged event sets `requires_reconciliation` and cannot be credited again automatically.

## Security boundaries

- Read-only Bitcoin RPC only.
- No private keys or seed phrases.
- No signing or broadcast RPCs.
- Exact integer satoshi accounting; no float amounts.
- Exact Bitcoin Core confirmation count; no confirmation estimates based on block time.
- Explicit watched-address to owner/intention mapping; no sender-address attribution.
- Identity conflicts fail closed.
- Durable SQLite event store and chain-tip checkpoint.

## Node requirements for later live integration

Recommended local Bitcoin Core configuration after wallet backup:

```ini
server=1
prune=0
txindex=1
rpcbind=127.0.0.1
zmqpubhashblock=tcp://127.0.0.1:28332
zmqpubrawtx=tcp://127.0.0.1:28333
zmqpubsequence=tcp://127.0.0.1:28334
```

RPC port 8332 must not be exposed to the public Internet.

## Existing code migration notes

`btc_pledge_watcher.py` remains unchanged in this PR. It currently has legacy public-API fallbacks and txid-level processed state. A later integration PR should make the local bitcoind observer canonical and keep public providers only as non-authoritative diagnostics/fallback evidence.

`bip32_deposit_manager.py` is also unchanged. Its current source explicitly labels key/address derivation as simplified. It must **not** be used to create production Bitcoin custody/deposit addresses. Production watched addresses must come from Bitcoin Core/descriptors or another independently validated Bitcoin key-management path.

## Next PR after this foundation

1. Local Bitcoin RPC client with cookie/rpcauth support and no write methods.
2. Local ZMQ ingestion for tx/block/sequence signals.
3. Reconciliation scanner against the durable checkpoint.
4. Registration table for real Bridge/Earn deposit intents and watched addresses.
5. Adapter from `confirmed` events into a separate idempotent credit workflow.
6. No withdrawals/signing until the observer is proven with real mainnet deposit confirmations and reorg/replay tests.
