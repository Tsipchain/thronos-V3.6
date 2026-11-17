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

An unconfirmed transaction removed from the mempool for a non-block reason is marked `dropped`. If the same `txid:vout` reappears, the idempotent observer may return it to `seen`.

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

BTC_ADAPTER_URL=https://thronos-btc-api-adapter-production.up.railway.app
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

## Pre-deposit hardening checkpoint

Before any real BTC test, run:

```powershell
python -m services.btc_node_agent --probe-zmq 10
```

The probe verifies Bitcoin Core reports pubhashblock, pubrawtx, and pubsequence, connects only to loopback ZMQ endpoints, and performs no signing, broadcast, crediting, or wallet mutation.

The live agent now tracks Bitcoin Core's per-topic ZMQ message sequence. A detected gap persists `zmq_gap_detected=1` and `observer_reconciliation_required=1`.

Sequence handling:
- A: recover/observe a mempool transaction using read-only getrawtransaction.
- R: mark unconfirmed watched outputs as dropped.
- C: block-connect processing remains driven by hashblock.
- D: mark reconciliation required and re-check canonical block hashes.

On live startup, recent blocks between the durable checkpoint and current tip are replayed with getblock verbosity 2. Replay is bounded by `BTC_BACKFILL_MAX_BLOCKS` (default 144) and fails closed on checkpoint reorg or an excessive gap.

### Remaining limitation before automatic production credit

A watched transaction that entered the mempool entirely while the agent was offline and remains unconfirmed when the agent restarts is not yet guaranteed to be discovered by startup recovery. For the first controlled mainnet observation test, start the live agent before broadcasting the BTC transaction and keep automatic Bridge/Earn credit disabled.

A later production-hardening phase should add either a bounded startup mempool snapshot scan or a dedicated Bitcoin Core descriptor/watch-only wallet reconciliation path.

## Confirmed-deposit outbox contract

Confirmed detection and balance credit are deliberately separated.

The local observer now uses a durable SQLite outbox keyed by:

`main:txid:vout`

Before an event can enter the outbox it must:
- be in `confirmed` state;
- meet `BTC_MIN_CONFIRMATIONS` (default 6);
- have a canonical block hash and height;
- have no event-level reconciliation requirement;
- have no global `observer_reconciliation_required` or `zmq_gap_detected` flag.

The observer database is bound to the Bitcoin network identity from block 0. Reusing the same SQLite database with another network/genesis fails closed. Every configured watched address is also checked by the local mainnet Bitcoin Core using read-only `validateaddress`.

Outbox delivery is disabled by default:

```text
BTC_DEPOSIT_DELIVERY_ENABLED=0
```

When explicitly enabled, the local agent POSTs authenticated confirmed-deposit observations to the adapter's `/api/node-agent/deposits` endpoint. Delivery is retried from the durable outbox. The adapter must acknowledge the same `main:txid:vout` idempotency key.

An adapter acknowledgement means only **durable receipt**. It must report `credit_applied=false`. No Bridge/Earn balance mutation is part of this observer/outbox lane.

The adapter deposit endpoint must remain disabled/fail-closed until its SQLite database path is backed by persistent storage. A transient container filesystem is not sufficient for production idempotency.

### Liveness

The node agent sends an independent adapter heartbeat every `BTC_ADAPTER_HEARTBEAT_SECONDS` (default 30 seconds), even when no Bitcoin block arrives. Heartbeats do not advance the observer block checkpoint.

### Current production boundary

Even after outbox acknowledgement is proven, automatic Bridge/Earn credit remains OFF until the downstream accounting ledger implements the same idempotency key and a reviewed compensation policy for a previously acknowledged deposit that later loses Bitcoin finality.

