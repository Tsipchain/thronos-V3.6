# Wallet V1 centralized verifier compatibility gate

## Scope and dependency

This change is stacked on Wallet credential-security Draft PR #963. It changes
only verification of the top-level Wallet V1 service-request envelope. It does
not change wallet/key creation, recovery-kit encryption, THR address derivation,
pledge activation, pledge vaults, ledger balances, migration records, or the
DER-signed `/api/v1/tx/send` transaction contract.

The safe review order is #963 first, then this verifier change. Until #963 is
merged, this branch must remain a Draft and must not be deployed independently.

## Existing contracts intentionally retained

| Contract | Existing format | Verification behavior |
| --- | --- | --- |
| Web/PWA service request | `secp256k1_compact` (or absent on the oldest clients), 64-byte compact ECDSA | Exact historical `JSON.stringify(payload, Object.keys(payload).sort())` bytes are retained. |
| Wallet adapter service request | `compact_secp256k1_hex`, 64-byte compact ECDSA | Full adapter payload is included in the signed JSON. |
| Wallet transaction | DER ECDSA in `wallet_v1_production_final.py` | Unchanged. |
| Direct Wallet V1 identity | Signing key derives to the claimed canonical THR address | Retained and now enforced by the service-request boundary. |
| Migrated/bound identity | Active stored public-key binding authorizes the canonical address | Retained; pre-status binding records remain active, while explicitly inactive records fail closed. |
| Pledge lookup/migration | SHA256, historical SHA256d-labelled ASCII-hex formula, and `:auth` HMAC-labelled formula | Unchanged byte-for-byte in `server_ext.py`. |

The historical SHA256d-labelled value is:

```text
h1 = SHA256(secret UTF-8).hexdigest()
h2 = SHA256(h1 ASCII hex).hexdigest()
```

It is deliberately not reinterpreted as SHA256 over the first binary digest.

## Production caller map

`_verify_walletv1_new_format()` is the existing top-level service-envelope
boundary used by swap, pool, digital-legacy and music-tip integrations. It now
delegates to `verify_wallet_v1_signed_request()` for:

- SEC1 public-key validation;
- real secp256k1 ECDSA verification;
- canonical or active-bound signer identity checks;
- five-minute timestamp freshness;
- atomic replay rejection through Redis when configured, with a persistent
  SQLite unique-key fallback for legacy single-node installations.

The existing signed-transaction path in `wallet_v1_production_final.py`, pledge
watchers, pledge registration routes, recovery-kit code and migration modules
are not redirected or modified.

## Synthetic compatibility evidence

The gate uses synthetic keys, credentials, addresses and isolated data stores.
It covers:

- direct and bound Wallet V1 ECDSA verification;
- compressed and uncompressed SEC1 key normalization;
- forged address, unrelated key, wrong signature, timestamp and replay failure;
- actual server-boundary replay persistence;
- exact pledge hash golden vectors;
- all three pledge lookup hash variants;
- existing pledge migration returning the same canonical wallet twice;
- fresh synthetic BTC pledge plus repeated confirmation without a second wallet;
- fresh synthetic USDT pledge lookup plus duplicate external transaction denial;
- #963 recovery, reload, PIN, key-binding and headless-browser acceptance.

No real credential or production database is used.

## Known compatibility/security boundary

The deployed web/PWA v1 serializer applies its sorted-key replacer recursively.
For ordinary action payload keys this signs `payload:{}` rather than the inner
payload. The server preserves those exact bytes so existing signatures are not
silently invalidated. The verifier reports
`payload_cryptographically_bound=false` for this legacy contract and never
claims otherwise.

Therefore the legacy web contract is an explicit compatibility adapter, not the
final authorization contract for new financial actions. Production rollout of
payload-bound service authorization still requires a separately reviewed client
upgrade to the full-payload contract, acceptance evidence from PWA/APK/web, and
an operator-controlled retirement policy for the legacy contract. It must not
be removed during startup or by an implicit migration.
