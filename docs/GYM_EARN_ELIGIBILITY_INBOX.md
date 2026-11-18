# Gym → Earn eligibility inbox

Status: Draft, read-only, no reward or payout activation.

The standalone Train2Earn service already provides tenant-scoped athletes,
gym-authenticated progress and signed `T2E_ELIGIBILITY_ONLY` exports. The Earn
side previously had a pure receipt verifier but no durable replay-safe inbox.

`services/earn_gym_eligibility_inbox.py` adds that missing boundary:

- HTTPS-only server-to-server export reads;
- a dedicated `X-T2E-Earn-Export-Key` kept outside browsers;
- HMAC verification of every receipt;
- exact Earn-account, tenant and challenge binding;
- durable `event_id` idempotency;
- one eligibility record per user/tenant/challenge;
- deterministic restart and concurrent-delivery behavior.

Stored state is always `verified_eligibility_only`. Public results explicitly
return `credit_authorized: false` and `payout_enabled: false`. The inbox has no
dependency on the Earn THC ledger, wallet, BTC payout, staking or conversion
services.

## Still required before funded rewards

1. Review and merge the standalone tenant/check-in work independently.
2. Define a versioned, funded T2E reward budget and reservation ledger.
3. Approve conversion rules without treating T2E units as THC.
4. Add an auditable settlement coordinator with atomic idempotency.
5. Add operator-controlled activation and reconciliation procedures.

Until those controls exist, eligibility may be displayed but cannot create a
spendable reward or payout.
