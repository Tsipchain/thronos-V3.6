# Survival Relay — Design Document

## Overview

Survival Relay is a cooperative relay-scoring system for Crypto Hunters Midday.
Players form relay chains — each player completes a challenge segment and passes
the relay token to the next player.  The chain's combined score determines
rewards.  A broken chain (player fails or times out) ends the relay for all
downstream players.

## Core Mechanics

### Relay Formation

1. A **Relay Captain** creates a relay session (max 5 players).
2. The captain sets the **challenge tier** (Bronze / Silver / Gold / Diamond).
3. Players join by scanning a QR code or entering a relay code.
4. Once all slots are filled, the relay enters a 60-second countdown.

### Relay Execution

Each player receives a timed challenge segment in sequence:

| Tier    | Time per segment | Score multiplier | Entry stake (DRX) |
|---------|-----------------|------------------|-------------------|
| Bronze  | 120 s           | 1.0×             | 0                 |
| Silver  | 90 s            | 1.5×             | 10 DRX            |
| Gold    | 60 s            | 2.5×             | 50 DRX            |
| Diamond | 45 s            | 5.0×             | 200 DRX           |

- A player's segment begins when the previous player submits their answer.
- If a player's timer expires, the relay **breaks** — all downstream players
  receive zero for their segments but keep any partial score earned before break.
- The relay token carries the cumulative score forward.

### Scoring

```
relay_score = sum(segment_scores) × tier_multiplier × chain_bonus
chain_bonus = 1.0 + (0.1 × completed_segments)
```

A full 5-player Gold relay with perfect segments:
`(5 × 1000) × 2.5 × 1.5 = 18,750 points`

### Reward Distribution

- **Pool model**: Entry stakes fund a relay prize pool.
- **Distribution**: 70% to winning relay, 20% to second, 10% to third.
- **No-stake tiers (Bronze)**: Rewards come from the seasonal DRX allocation,
  not from player stakes.

## State Machine

```
FORMING → COUNTDOWN → ACTIVE → COMPLETED
                   ↘ BROKEN (if any segment times out)
                   ↘ CANCELLED (if captain cancels before start)
```

### Relay Record Schema

```json
{
  "relay_id": "relay_<uuid>",
  "tier": "gold",
  "captain": "THR...",
  "players": ["THR...", "THR...", "THR...", "THR...", "THR..."],
  "segments": [
    {"player": "THR...", "score": 950, "time_ms": 42300, "status": "completed"},
    {"player": "THR...", "score": 0, "time_ms": 60000, "status": "timeout"}
  ],
  "status": "broken",
  "break_at_segment": 2,
  "total_score": 950,
  "created_at": "2025-01-01T00:00:00Z"
}
```

## API Endpoints (future)

| Method | Path                              | Description                  |
|--------|-----------------------------------|------------------------------|
| POST   | `/api/relay/create`               | Captain creates relay        |
| POST   | `/api/relay/<id>/join`            | Player joins relay           |
| POST   | `/api/relay/<id>/submit-segment`  | Submit segment answer/score  |
| GET    | `/api/relay/<id>`                 | Relay state + live scores    |
| POST   | `/api/relay/<id>/cancel`          | Captain cancels (pre-start)  |

## Security Constraints

- Entry stakes are held in a relay escrow address, not the captain's wallet.
- Segment submissions are signed with the player's wallet key.
- Server validates segment timing server-side (client timestamps are untrusted).
- Anti-collusion: players cannot see each other's challenges.
- THRONOS_RELAY_REWARDS_ENABLED must be true to activate stake mechanics.
  When false, only Bronze (no-stake) relays are available.

## Dependencies

- Crypto Hunters Midday Phase 1 (hub card) — player discovery
- Capability bridge Phase 3 — wallet:request_challenge_signature for segment signing
- DRX token ledger (existing in addons/crypto_hunters/backend)

## Not in Scope

- Cross-chain relay staking (DRX is Thronos-native only)
- Real-time WebSocket relay streaming (polling is sufficient for MVP)
- Automated matchmaking (captains form teams manually)
