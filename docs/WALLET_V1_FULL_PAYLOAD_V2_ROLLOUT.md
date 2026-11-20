# Wallet V1 full-payload signed request V2

Status: review-only. No production activation is authorized by this document.

## Contract

`signature_format=wallet_v1_full_payload_v2` signs the UTF-8 bytes of a JSON
object whose keys are recursively sorted and whose separators are exactly `,`
and `:`. The signed object contains only:

- `protocol_version`: `"2"`
- `domain`: `"thronos.wallet.service_request"`
- `chain_id`: `"thronos-mainnet"`
- normalized `action`
- `canonical_v1_address`
- `signer_address` derived from the signing public key
- the complete nested `payload`
- `issued_at`, `expires_at`, and `nonce`

Arrays retain their order. Payload numbers are transmitted as decimal strings.
Payload booleans, strings and null are preserved. Native JSON numbers in a V2
payload fail closed at the Python verifier. Maximum TTL is 300 seconds; the web
builder currently uses 120 seconds. ECDSA is secp256k1 over SHA-256 and the wire
signature is compact `r || s` hex.

The public key must derive either to the canonical address or to the active,
server-recorded signer binding for that canonical address. The claimed signed
`signer_address` must equal the derived signer. The existing atomic nonce store
is consumed only after signature, identity, time, domain, version and network
validation.

## Execution-route audit

Every V2 route first creates a trusted execution object from an exact
action-specific payload schema. Any other top-level field, mismatched `from`,
missing required signed field or signed constraint that the handler does not
implement is rejected before ECDSA verification and nonce consumption. The
handler verifies the original envelope, but executes only the trusted object.

| Route | Values derived from the signed envelope | Independently authoritative values | Release decision |
|---|---|---|---|
| `/api/swap/execute` | canonical trader, token pair, input amount, minimum output | selected pool/route, current reserves, actual output and pool fee | V2 handler **GO for staging**; unsupported quote/pool aliases fail closed |
| `/api/v1/pools` POST | canonical provider, token pair, both deposits, requested fee | supported-token policy and ledger balances | V2 handler **GO for staging**; mobile client coverage required |
| `/api/v1/pools/add_liquidity` | canonical provider, pool ID, both deposits, referrer | pool record, reserves, share calculation and balances | V2 handler **GO for staging**; unsupported quote/slippage aliases fail closed |
| `/api/v1/pools/remove_liquidity` | canonical provider, pool ID and shares | provider position, pool reserves and calculated outputs | V2 handler **GO for staging**; unsupported quote/min-output aliases fail closed |
| `/api/v1/music/tip` | canonical sender, track ID, amount, asset, duration/GPS telemetry | track registry and its artist recipient, ledger balance and service fee | V2 handler **GO for staging**; native client upgrade required |
| `/api/legacy/create`, `/ping`, `/claim` | canonical owner/heir, complete legacy definition, claimed owner | stored legacy record, inactivity state, percentage and ledger balance | V2 handlers **GO for staging**; client/device coverage required |
| `/api/v1/pools/swap` | pledge mode plus legacy credential/whitelist logic | Not migrated to the V2 service-request boundary | **NO-GO** as a Wallet V1 ECDSA-authorized action |
| `/api/v1/pools/add-liquidity` | separate Wallet Action Intent V1 plus payload hash, or explicit legacy credential | Separate signed-intent contract, not silently treated as this V2 contract | Independently review before convergence |
| `/api/wallet/send`, `/api/wallet/internal-transfer` | separate canonical transaction / intent signatures and nonce checks | Not changed | Keep separate; regression-test before release |
| staking, bridge and withdrawal mutation routes | route-specific credentials, intents and operator gates | Not changed and not represented as V2-covered | **NO-GO** under this contract until separately audited |

The verifier continues to parse historical `secp256k1_compact` and
`compact_secp256k1_hex` envelopes for compatibility diagnostics. Financial
entry points using the new top-level Wallet V1 envelope require contract V2;
a valid signature over the old `payload:{}` bytes returns an explicit client
upgrade error. Existing field-bound `signed_tx` and credential-based legacy
routes remain version-separated and are not reinterpreted as V2 authorization.

## Client dependency and rollout

1. Keep the PR unmerged while web, installed PWA and native APK builds are
   tested against a production-like staging copy with synthetic ledgers.
2. Web receives the V2 builder and compact runtime signer in the same release.
3. The installed PWA receives and precaches the shared canonicalization module.
   Its emergency direct `/api/swap/execute` fallback now emits V2; its primary
   Wallet Action Intent swap remains a separate, explicitly versioned contract.
4. The React Native APK currently posts its own `SignedTxEnvelope`; it does not
   yet emit this V2 envelope. Do not claim APK V2 support until a separately
   reviewed client change and device test exist.
5. Exercise direct and bound/migrated wallets for swap, add/remove liquidity,
   pool creation, tip and digital-legacy actions. Confirm old explicit legacy
   clients continue only through their documented legacy route.
6. Release server and compatible clients in one approved window. Monitor only
   version/error counts; never log signatures, payload secrets, PINs or keys.
7. Rollback is code rollback to the reviewed pre-V2 revision. It does not alter
   wallet keys, address bindings, pledge records, nonce history, recovery kits
   or ledgers. Do not add a runtime downgrade from a failed V2 request.

Source audit details for native clients:

- `thronos-wallet-app/src/services/api.ts` wraps swap data as `{tx: signedTx}`
  and remove-liquidity data as `{pool_id, shares, tx}`; neither is the V2
  envelope accepted by the reviewed routes.
- `thronos-wallet-app/src/screens/PoolsScreen.tsx` still sends `auth_secret` to
  the separate legacy add-liquidity route.
- `mobile-sdk/src/api.js` forwards caller-provided swap objects and constructs
  an unsigned legacy music-tip body. The Android and iOS SDK sources expose
  older wallet-secret send flows and contain no V2 action builder.
- The browser extension constructs its historical `{tx: ...}` swap envelope.

Therefore Android, iOS, the standalone mobile SDK and the browser extension
are **NO-GO for V2 financial actions** until independently reviewed client PRs
emit this exact contract and complete device tests. Their explicit legacy
contracts remain unchanged by this server PR; no failed V2 request may fall
back to them.

### Operator-approved deployment and rollback gate

1. Approve and merge dependency order `#963 -> #964 -> #965`; do not squash or
   reorder their security boundaries without repeating the full gate.
2. Deploy only to an isolated environment with synthetic ledgers, the same
   Redis topology as production and paid/broadcast execution disabled.
3. Record reviewed server and web/PWA/native build SHAs. Confirm the client
   emits `wallet_v1_full_payload_v2` for each action it exposes.
4. Run recovery/unlock, pledge golden vectors, all route mutations, slippage,
   replay/concurrency, account switch and offline/update/reload acceptance.
5. Back up persistent application data before an operator-authorized production
   release. This PR has no data migration and requires no database rewrite.
6. Release compatible server and clients in one window. Monitor aggregate
   action/version/error counters only; never log credentials or envelopes.
7. On unexpected authorization errors, disable the affected action and roll
   application code back to the recorded revision. Do not clear nonce storage,
   bindings, recovery material, pledge records or ledgers, and do not enable a
   legacy fallback for a failed V2 request.

## Broad Wallet baseline: 27 remaining failures

These failures were present on the dependency baseline and remain release
evidence gaps; none is hidden or deleted by this PR.

| Count | Area | Impact classification |
|---:|---|---|
| 5 | activation-check fixture lacks `server_module` | test-fixture/configuration failure; activation coverage unavailable |
| 1 | crypto HMAC guard ordering expectation | stale expectation against the hardened explicit-version order |
| 1 | execution-engine test expects an invalid signature to execute | unsafe stale expectation; production must continue to reject |
| 3 | frontend auth source-string expectations | stale fixture assertions, not runtime execution evidence |
| 8 | pool backend tests patch removed `wallet_v1_production_final` symbol | stale fixture; route runtime coverage is supplied separately here |
| 8 | swap backend fixtures omit current quote legs or expect historical status bodies | stale/incomplete route fixtures; runtime V2 swap and slippage are covered separately here |
| 1 | THR reconciliation lacks test `ADMIN_SECRET` | test-environment configuration failure (HTTP 503) |

Because the activation and native-client gaps remain, the overall Wallet V1
production decision is **NO-GO**, even though the V2 handlers above are ready
for an isolated staging run.

## Intentionally unchanged

BTC/USDT pledge addresses and watchers; historical SHA256, SHA256d-labelled and
`:auth` lookup bytes; canonical THR address derivation; key bindings; recovery
kits; migrated identities; balances; history; staking/liquidity economics; and
all production data are unchanged.

## Activation evidence still required

- Production-like staging execution through each actual financial route with
  synthetic balances (local real-handler tests and Chromium builder/verifier
  acceptance are green; an independently deployed staging run is still due).
- Installed PWA reload/offline/update test for the new precached contract.
- Android and iOS build/device evidence for every action exposed by the app.
- Staging concurrency and rollback exercise against a real shared Redis. Unit
  coverage proves Redis `SET NX` and shared-SQLite exactly-once semantics, but
  does not replace a multi-process deployment test.
- Operator approval after #963 and #964 are approved in dependency order.

