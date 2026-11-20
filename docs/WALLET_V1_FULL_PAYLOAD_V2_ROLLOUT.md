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

| Route | Current authorization | V2 result | Release decision |
|---|---|---|---|
| `/api/swap/execute` | V2 top-level; field-bound legacy `signed_tx`; historical credential path | V2 nested token, amount, minimum output, quote/pool fields are signed; top-level shadow fields rejected | V2 path ready for staged QA; legacy contracts unchanged |
| `/api/v1/pools` POST | V2 or explicit legacy pool auth | V2 pool pair, amounts and fee are nested and signed | Web/mobile client coverage required |
| `/api/v1/pools/add_liquidity` | V2 or explicit legacy pool auth | V2 pool, both amounts, referral, quote and slippage fields are signed; V1 UI no longer downgrades | Web path ready for staged QA |
| `/api/v1/pools/remove_liquidity` | V2 or explicit legacy pool auth | V2 pool, shares, minimum outputs and quote fields are signed | Client upgrade required |
| `/api/v1/music/tip` | V2 or explicit legacy credential auth | V2 track, asset, amount and duration are signed | Web path ready for staged QA |
| `/api/legacy/create`, `/ping`, `/claim` | V2 required by these endpoints | New top-level Wallet V1 requests require V2; claim owner and legacy definition are nested | Client upgrade and isolated regression required before release |
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

## Intentionally unchanged

BTC/USDT pledge addresses and watchers; historical SHA256, SHA256d-labelled and
`:auth` lookup bytes; canonical THR address derivation; key bindings; recovery
kits; migrated identities; balances; history; staking/liquidity economics; and
all production data are unchanged.

## Activation evidence still required

- Production-like staging execution through each actual financial route with
  synthetic balances (the real Chromium builder/verifier acceptance is green).
- Installed PWA reload/offline/update test for the new precached contract.
- Android and iOS build/device evidence for every action exposed by the app.
- Staging concurrency and rollback exercise using the same durable nonce-store
  topology as production.
- Operator approval after #963 and #964 are approved in dependency order.

