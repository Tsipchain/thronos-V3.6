# Reward Contract — Design Document

## Overview

The Reward Contract governs how DRX game tokens are minted, distributed, and
(optionally) converted to THR.  It defines emission schedules, anti-abuse rules,
and the boundary between game-internal currency and on-chain value.

## Principles

1. **No automatic THR payouts.** DRX → THR conversion requires explicit user
   action and admin approval.  THRONOS_RELAY_REWARDS_ENABLED must be true.
2. **No promised returns.** DRX carries no guaranteed financial value.  Sponsor
   disclosure in the PWA makes this clear.
3. **Capped emission.** Daily DRX minting is bounded to prevent runaway inflation.
4. **Transparent ledger.** All DRX movements are recorded in the game ledger
   with full audit trail.

## Emission Schedule

### Daily Caps

| Source              | Max DRX / day | Notes                              |
|---------------------|--------------|-------------------------------------|
| Challenge rewards   | 10,000       | Per-player cap: 500 DRX / day      |
| Relay completion    | 5,000        | Split across relay participants     |
| Seasonal events     | 20,000       | Time-limited campaigns              |
| Referral bonuses    | 2,000        | One-time per referred player        |
| **Total**           | **37,000**   |                                     |

### Per-Player Limits

- Max 500 DRX earned per player per 24h rolling window.
- Max 10 DRX per single challenge submission (existing cap in server.py).
- Relay rewards are additional but still within the daily player cap.

## DRX Ledger Schema

```json
{
  "player": "THR...",
  "balance": 1250.0,
  "lifetime_earned": 4800.0,
  "lifetime_spent": 3550.0,
  "last_earn_at": "2025-01-01T12:00:00Z",
  "daily_earned": 120.0,
  "daily_reset_at": "2025-01-02T00:00:00Z"
}
```

## Reward Transaction Types

| Type                 | Direction | Description                        |
|----------------------|-----------|------------------------------------|
| `challenge_reward`   | mint      | Score-based reward from challenge  |
| `relay_reward`       | mint      | Relay completion bonus             |
| `seasonal_bonus`     | mint      | Event/campaign reward              |
| `referral_bonus`     | mint      | New player referral                |
| `item_purchase`      | burn      | In-game item bought with DRX      |
| `drx_to_thr_convert` | burn      | Conversion to THR (admin-gated)   |
| `admin_adjustment`   | either    | Manual correction by admin         |

## DRX → THR Conversion (Future, Gated)

### Prerequisites

- `THRONOS_RELAY_REWARDS_ENABLED=true` (currently false, must stay false)
- Player has completed KYC (pledge-based identity)
- Minimum conversion: 1,000 DRX
- Cooldown: max 1 conversion per 7 days per player

### Conversion Flow

1. Player requests conversion in PWA (Crypto Hunters screen)
2. Server creates a `drx_conversion_request` record (status: pending)
3. Admin reviews and approves/rejects via admin panel
4. On approval: DRX is burned, THR is minted to player's address
5. Conversion rate: set by admin, not fixed (market-based)

### Conversion Record

```json
{
  "id": "conv_<uuid>",
  "player": "THR...",
  "drx_amount": 1000.0,
  "thr_amount": 0.0,
  "rate": 0.0,
  "status": "pending",
  "requested_at": "2025-01-01T12:00:00Z",
  "reviewed_at": null,
  "reviewed_by": null
}
```

## Anti-Abuse Measures

### Rate Limiting

- Max 20 challenge submissions per hour per player.
- Max 5 relay participations per day per player.
- IP-based throttling: max 100 game API calls per minute per IP.

### Score Validation

- Server-side timing validation (client timestamps untrusted).
- Challenge answers are hashed and compared server-side.
- Anomaly detection: flag players with >95th percentile scores for manual review.

### Sybil Resistance

- One DRX account per THR address.
- THR address must have completed pledge (BTC or USDT) — ensures KYC.
- Referral bonuses require the referred player to complete at least 10 challenges.

## API Endpoints (future)

| Method | Path                          | Description                        |
|--------|-------------------------------|------------------------------------|
| GET    | `/api/game/drx/balance`       | Player's DRX balance + limits      |
| GET    | `/api/game/drx/history`       | DRX transaction history            |
| POST   | `/api/game/drx/convert`       | Request DRX → THR conversion       |
| GET    | `/api/game/drx/convert/<id>`  | Conversion request status          |
| POST   | `/api/admin/drx/approve/<id>` | Admin approves conversion          |

## Security Constraints

- THRONOS_RELAY_REWARDS_ENABLED must remain false until explicitly enabled.
- No automatic THR minting from game actions.
- DRX → THR conversion requires admin approval (no automatic payouts).
- Conversion rate is admin-set, never hardcoded or promised.
- All DRX transactions are logged with full audit trail.
- No private keys, wallet secrets, or seed phrases in game API payloads.

## Dependencies

- Existing game reward system (server.py `/api/game/submit_score`)
- Crypto Hunters Midday Phase 1 (PWA hub card)
- THR ledger (server.py `LEDGER_FILE`)
- Admin panel (existing `/game` route)

## Not in Scope

- Smart contract deployment (DRX is ledger-based, not ERC-20)
- External exchange listing for DRX
- Automated market maker for DRX/THR pair
- Cross-chain DRX transfers
