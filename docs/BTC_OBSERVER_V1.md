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

## Node requirements for live integration

The canonical local path is designed to work with a **synced pruned Bitcoin Core node**. A global txindex is not required for Observer v1.1 because live transactions arrive through ZMQ and confirmed transactions are reconciled from freshly announced blocks using `getblock(..., 2)`.

Recommended local Bitcoin Core configuration:

```ini
server=1
rpcbind=127.0.0.1
rpcallowip=127.0.0.1
zmqpubhashblock=tcp://127.0.0.1:28332
zmqpubrawtx=tcp://127.0.0.1:28333
zmqpubsequence=tcp://127.0.0.1:28334
```

Pruning may remain enabled. `txindex=1` is intentionally **not required** for this phase.

RPC port 8332 must never be exposed to the public Internet. The local node agent accepts only loopback Bitcoin RPC/ZMQ and pushes outbound authenticated HTTPS state to the Thronos BTC adapter.

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


## Local node-agent flow

```text
Bitcoin Core (mainnet, synced, pruning allowed)
  -> localhost RPC + ZMQ
  -> services/btc_node_agent.py
       -> durable SQLite observer/checkpoint/sequence
       -> watched output detection
       -> confirmation + reorg reconciliation
       -> outbound authenticated HTTPS only
  -> btc-api.thronoschain.org
```

The node agent uses a read-only RPC whitelist. It has no signing, wallet-unlock, private-key, transaction-creation, or broadcast method.

### Local environment

```text
BITCOIN_RPC_URL=http://127.0.0.1:8332
BITCOIN_RPC_COOKIE_FILE=<optional explicit .cookie path>
BITCOIN_RPC_USER=<optional; use with password>
BITCOIN_RPC_PASSWORD=<optional; use with user>

BTC_ZMQ_HASHBLOCK=tcp://127.0.0.1:28332
BTC_ZMQ_RAWTX=tcp://127.0.0.1:28333
BTC_ZMQ_SEQUENCE=tcp://127.0.0.1:28334

BTC_ADAPTER_URL=https://btc-api.thronoschain.org
BTC_ADAPTER_NODE_AGENT_TOKEN=<secret; never commit>
BTC_OBSERVER_DB=./data/btc_observer.db
BTC_WATCH_REGISTRY=./data/btc_watch_registry.json
```

If no watch registry is configured, the agent can still perform node preflight and publish authoritative tip state; deposit discovery remains disabled until explicit watched-address intents exist.

A one-shot preflight can be run with:

```bash
python -m services.btc_node_agent --once
```

Do not run the live agent against production adapter ingest until the adapter PR containing the authenticated node-agent endpoints is merged, deployed, and its token is configured on both sides.
