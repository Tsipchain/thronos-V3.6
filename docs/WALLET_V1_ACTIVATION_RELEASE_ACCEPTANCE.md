# Wallet V1 activation and release acceptance

Status: review-only stacked correction after `#963 -> #964 -> #965`. No merge,
deployment, production data mutation or financial execution is authorized.

## Broad-suite closure

Baseline at `#965` head `7018744c51250c0a582eccfba882d0a306793454`:
`915 passed, 27 failed` from 942 collected Wallet tests.

| Previous failures | Root cause | Corrected evidence |
|---:|---|---|
| 5 | activation tests patched removed `activation.server_module` instead of the authoritative `activation._server()` resolver | real-route ECDSA tests patch only synthetic pledge/migration records |
| 1 | crypto test selected an earlier read-only swap fetch instead of the post-signing fetch | search is scoped after signed-envelope creation |
| 1 | execution-adapter test omitted the now-required activation boundary | adapter test explicitly isolates admission; real admission is tested separately |
| 3 | frontend source assertions described pre-hardening wrappers/storage syntax | assertions now preserve async signing, canonical address resolution and constant-key session cleanup |
| 8 | pool tests patched a removed `server.wallet_v1_production_final` attribute | tests patch the module function actually imported at runtime |
| 8 | swap fixtures used the old quote shape/status assumptions | fixtures now contain authoritative `legs`; signed action wins over irrelevant unsigned `option`; fail-closed 400 responses and zero mutation are asserted |
| 1 | reconciliation dry-run supplied an empty ambient admin secret | test installs and submits a synthetic non-empty operator secret, preserving fail-closed production behavior |

After correction: `943 passed, 0 failed`. The extra test is a distinct migrated
old-address read-only case. No production Python/JavaScript behavior changed.

## Activation route evidence

The tests use the actual `/api/v1/tx/send` route and actual secp256k1 verifier.
Only synthetic pledge/migration state and the final ledger executor are
isolated.

- active USDT/BSC pledge state: admitted;
- active BTC pledge state: admitted;
- completed migrated canonical address: admitted;
- completed/repaired old address: `legacy_address_migrated_read_only`;
- unpledged and unapproved address: `inactive_thr_address`;
- cryptographically modified envelope: rejected before activation/execution;
- read-only replica: rejected before signature/admission/execution;
- repeated BTC confirmation: one canonical wallet record;
- repeated USDT transaction: duplicate rejected; historical SHA256 and `:auth`
  bytes remain unchanged;
- SHA256, historical SHA256d-labelled and `:auth` lookup golden vectors remain
  accepted.

## Production-like staging evidence

All state was ephemeral and synthetic.

| Boundary | Evidence | Status |
|---|---|---|
| restore, unlock, account switch, cancellation | real headless Chromium Wallet gate | PASS |
| BTC/USDT pledge and migration compatibility | route golden vectors and duplicate tests | PASS |
| V2 signing and authorization | real ECDSA, trusted execution schemas and tamper tests | PASS |
| swap, pool create/add/remove, music tip, digital legacy | actual Flask handlers with synthetic ledgers | PASS |
| shared multi-instance replay | Redis 7.4, 8 independent processes, 16 concurrent attempts: one accepted | PASS |
| installed PWA install/update/offline reload | actual Chromium service worker, V2 precache, cache upgrade and offline reload | PASS |
| Android/iOS device execution | source inventory only | NOT COMPLETE |

The real-Redis test is opt-in through `WALLET_REAL_REDIS_URL`; CI collects it
but skips it unless an isolated Redis is explicitly supplied. The normal CI
still tests the Redis `SET NX` contract and shared-SQLite fallback.

## Mobile financial-action inventory

The native sources do not yet implement `wallet_v1_full_payload_v2`. Existing
contracts are inventoried, not silently replaced.

| Mobile action | Current request contract | Release status |
|---|---|---|
| THR/custom-token send | `SignedTxEnvelope` inside `{tx}` to `/api/v1/tx/send` | separate centralized transaction contract; device QA required |
| pledge stake | `{tx: SignedTxEnvelope}` | separate signed transaction; not V2-reviewed |
| swap | `{tx: SignedTxEnvelope}` to `/api/swap/execute` | incompatible with reviewed V2 route; NO-GO |
| governance vote | proposal/vote plus `{tx: SignedTxEnvelope}` | separate contract; audit required |
| bridge execute/burn | chain/destination plus `{tx: SignedTxEnvelope}` | separate contract; bridge remains disabled/NO-GO |
| pool remove | unsigned pool/shares plus `{tx: SignedTxEnvelope}` | does not match V2 envelope; NO-GO |
| music tip | unsigned address/track/artist/amount body | does not match V2 authorization; NO-GO |
| cross-chain add liquidity | legacy `auth_secret`/passphrase request | explicit legacy contract; NO-GO for V2 activation |
| withdrawal | address plus `send_secret` and destination | separate legacy payout contract; withdrawals remain disabled |
| add liquidity, token creation, NFT mint/buy | request contains `private_key_hex` | security blocker; MUST NOT be production-enabled |
| Pythia deposit/withdraw intent | unsigned accounting request | separate settlement boundary; NO-GO for financial execution |
| BTC/USDT pledge registration, lookup, migration/recovery | historical pledge/recovery contracts | intentionally preserved; not reinterpreted as V2 |

The standalone JavaScript mobile SDK forwards caller-provided legacy swap
objects and constructs unsigned music-tip requests. The native Kotlin/Swift
SDKs retain older wallet-secret send contracts. All require independent client
PRs and Android/iOS device evidence before V2 financial activation.

## Release decision

Activation coverage and the reviewed browser/PWA server paths are ready for
review. Overall production activation remains **NO-GO** until:

1. `#963`, `#964`, `#965` and this stacked correction are approved in order;
2. Android/iOS V2-compatible action PRs remove any network transmission of
   private signing keys and pass real-device tests;
3. the shared production-like Redis topology is exercised in the approved
   staging deployment, not only the local isolated container;
4. operator-approved rollback evidence and monitoring are recorded; and
5. no financial action is enabled until its exact client/server contract is
   independently approved.
