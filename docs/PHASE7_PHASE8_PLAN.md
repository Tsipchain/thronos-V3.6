# Phase 7–9 Technical Plan (Draft)

## Scope

This document captures the **design plan** requested in the latest feedback so we can move into
implementation in Phase 2. It does **not** introduce runtime changes; it is a blueprint for the
next iteration.

---

## 1) Distributed Merkle Tree & Parallel Validation

### Goals
- Break the current O(n²) `mine_block()` Merkle calculation into **batched subtree builds**.
- Allow miners/ASICs to compute subtrees in parallel and return subtree roots.
- Aggregate subtree roots into a single `merkle_root` in a lightweight coordinator.
- Reward first K miners that validate the proposed block in a round.

### Proposed Flow
1. **Batch Partition**: split pending transactions into fixed-size chunks (e.g., 256).
2. **Subtree Jobs**: each chunk → worker computes a subtree root and a compact proof.
3. **Aggregator**:
   - Collect subtree roots
   - Build top-level tree from the roots only
   - Emit final `merkle_root`
4. **Parallel Validation**:
   - Workers receive the final block header + subtree proof
   - First K validators submit signed “valid” attestations
   - Master includes attestation list in block metadata

### Data Structures (Draft)
```json
{
  "subtree_job": {
    "job_id": "J-...",
    "tx_ids": ["...", "..."],
    "subtree_root": "0x...",
    "proof": ["0x...", "..."],
    "worker": "miner-id",
    "signature": "..."
  }
}
```

---

## 2) State Root Snapshots & Mempool Pre‑Validation

### Goals
- Every 1000 blocks, compute a **state root** (addresses + balances).
- Store checkpoint metadata and root for fast bootstrap.
- Pre‑validate transactions by miners before mempool insert.

### Proposed Flow
1. **Checkpoint cadence**: `HEIGHT % 1000 == 0`.
2. **State Root**:
   - Build a Merkle tree over ordered `(address, balance)` pairs.
   - Persist `state_root` + `height` + timestamp.
3. **Mempool Pre‑Validation**:
   - Miners sign a “pre‑valid” attestation after verifying balance/signature/nonce.
   - Master accepts transaction into mempool only with N attestations or whitelisted miners.

### Draft checkpoint schema
```json
{
  "height": 23000,
  "state_root": "0x...",
  "timestamp": "2026-07-10T12:00:00Z",
  "total_accounts": 120345
}
```

---

## 3) BLS Aggregation Integration (Quorum Consensus)

### Goals
- Use existing `quorum_consensus_bls.py` for **block-level signatures**.
- Produce a single aggregated signature per consensus round.

### Proposed Flow
1. Proposer emits block header hash.
2. Validators sign header hash via BLS.
3. Aggregator combines signatures → `agg_signature`.
4. Block includes `agg_signature` + validator bitmap.

---

## 4) Reed‑Solomon Encoded Block Storage

### Goals
- Reduce disk requirements and increase data availability.
- Store shards across miners and reconstruct blocks from a subset.

### Proposed Flow
1. Encode block into N shards with threshold K.
2. Distribute shards to miners.
3. Master verifies availability via **proof‑of‑data‑availability** (PoDA).

---

## 5) AI Telemetry → Parquet Pipeline + Predictions

### Goals
- Convert compressed JSONL telemetry into Parquet.
- Train models for route prediction and music recommendations.
- Expose `/api/ai/predict/route`.

### Proposed Flow
1. **Ingest**: JSONL → staging area
2. **Transform**: schema normalization + partitioning (day, region, wallet)
3. **Store**: Parquet in `/data/telemetry_parquet/`
4. **Train**: lightweight models first (regression), expand to seq models later
5. **Serve**: `POST /api/ai/predict/route` with origin/destination

---

## 6) Automated Bitcoin Bridge (Phase 7)

### Goals
- Multi‑sig WBTC reserves
- On‑chain monitoring of deposits/withdrawals
- THR ↔ WBTC burn/mint contracts
- Lightning Network interoperability design

### Proposed Workstreams
1. **Reserves**: multi‑sig wallet with threshold signatures.
2. **Monitoring**: watcher service with confirmation policies.
3. **Mint/Burn**: on‑chain contract operations.
4. **Lightning**: design for HTLC‑style lock/unlock with off‑chain tracking.
5. **Ethereum L2**: outline bridging to Arbitrum/Optimism.

---

## 7) Wallet SDK Unification

### Goals
- Identify shared modules across web/mobile/extensions.
- Package a single SDK for address handling, signing, session management.
- Remove duplicated wallet flows and reduce timers.

### Proposed Steps
1. Inventory existing wallet modules.
2. Extract common utilities into `/public/static/`.
3. Add versioned entry points for web, mobile, extension.
4. Replace `setInterval` polling with event‑driven signals where possible.

---

## 8) Phase 8–9 Preparation

### Goals
- AI Model Marketplace + API Credits (THR payments)
- Multi‑region nodes + IBC messaging architecture

### Proposed Workstreams
1. Payment rails & credits ledger with on‑chain settlement.
2. Marketplace service for AI model discovery & usage.
3. Regional deployment strategy and inter‑node messaging.

---

## Next Step (Phase 2)

Begin implementation of sections (1) and (2), starting with:
- Merkle subtree job schema and coordinator.
- State root snapshots at block cadence.
- Mempool pre‑validation attestation API.
