# Canonical Paid-Ad Publisher Integration Contract

This contract applies to Earn, Wallet Earn, Basketball Market, and future
approved publishers. Browser-reported viewability is **not cryptographically
proven**. The canonical service combines authenticated publisher relays,
server-timed observation challenges, signed delivery proofs, bounded browser
claims, rate limits, durable idempotency, and accounting audits. Invalid or
incomplete evidence charges zero THC.

## Required server-side relay

Publisher credentials must remain server-side. Browser code must call its own
publisher backend; it must never receive `EARN_PUBLISHER_SECRET`.

1. The publisher backend requests `/api/earn/ads/serve` with its registered
   publisher ID, canonical placement, opaque viewer hash, and
   `X-Publisher-Key`.
2. When `IntersectionObserver` reports at least 50% visibility while
   `document.visibilityState === "visible"`, the browser asks its backend to
   start an observation.
3. The backend relays the proof to `/api/earn/ads/serve/observation` with
   `X-Publisher-Key`, then returns the observation ID/token and `not_before_ms`.
4. Continuous qualifying visibility for at least 1,000 ms is required. Losing
   visibility, dropping below 50%, navigation, or component unmount cancels the
   local timer; no view event is sent.
5. The backend relays `/api/earn/ads/serve/event` with both proof and
   observation credentials, the bounded browser measurements, and
   `X-Publisher-Key`.
6. Clicks use the same authenticated event relay but require no observation and
   always charge zero THC.

The canonical service verifies publisher and placement state, proof signature,
proof/observation publisher-placement-viewer binding, server elapsed time,
expiry, browser-claim bounds, frequency/rate limits, and exact-once event state
inside one database transaction.

## Consumer dependency map

| Consumer | Current implementation | Required change | Activation state |
|---|---|---|---|
| Thronos Earn | Canonical API exists; no current paid frontend consumer found | Add a reviewed relay and observation-aware component before registering a paid Earn placement | Blocked/fail closed |
| Wallet Earn | No canonical paid frontend consumer found | Add a reviewed relay/component only in the non-sensitive Earn surface; transaction, signing, seed, key, transfer and approval screens remain excluded | Blocked/fail closed |
| Basketball Market | Existing FastAPI relay and three React consumers | Add authenticated observation/event relays and continuous 1-second visibility measurement in its own Draft PR | Blocked until matching PR |

House-ad fallback may continue where already designed. A missing secret,
observation, measurement, binding, or active placement must never fall back to
paid billing.

## Audit and privacy

Accepted events record proof, observation, publisher, placement, opaque viewer,
server elapsed time, browser-claim marker, price version, charge, treasury and
reservation effects. Rejections record a bounded reason and opaque identifiers;
secrets, raw IP addresses, user agents, private keys and wallet material are
never logged.
