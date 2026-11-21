# Wallet V1 Native V2 release gate

Status: Draft / no production activation

This change is stacked on Draft PRs `#963 -> #964 -> #965 -> #966`. It does not
change Wallet V1 address derivation, BTC or USDT pledge derivation, historical
credential hashes, recovery-kit encryption, balances, or transaction history.

## Mobile action matrix

| Action | Native contract | Release state |
|---|---|---|
| THR/token transfer | Existing `SignedTxEnvelope` | Staging only |
| Swap | Wallet V1 full-payload V2 | Staging only |
| Internal pool add/remove | Wallet V1 full-payload V2 | Staging only |
| Music tip | Wallet V1 full-payload V2 API available | UI integration pending |
| Token creation | Wallet V1 full-payload V2 | Staging only |
| NFT mint | Wallet V1 full-payload V2 with signed maximum mint fee | Staging only |
| NFT buy | Wallet V1 full-payload V2 with signed maximum price | Staging only |
| Staking | No reviewed V2 execution contract | Disabled / NO-GO |
| Governance vote | Existing server route uses legacy credential auth | Disabled / NO-GO |
| Bridge deposit/withdrawal | No reviewed native V2 execution contract | Disabled / NO-GO |
| Cross-chain liquidity | No shared V2 nonce boundary | Disabled / NO-GO |
| Pythia deposit/withdraw intent | Unsigned accounting route | Disabled / NO-GO |
| External withdrawal | Legacy credential route only | Disabled / NO-GO |

Disabled actions throw before a network request. A failed V2 request is never
retried with legacy credentials, and mutating HTTP requests are never retried
against the replica.

## Security boundary

- React Native derives Bitcoin P2PKH addresses locally. The former server route
  that accepted `private_key_hex` returns HTTP 410.
- V2 envelopes bind domain, protocol and chain, action, canonical wallet,
  derived signer, complete normalized payload, issuance/expiry, and nonce.
- The backend derives execution values only from the verified payload or from
  authoritative server state. NFT purchase price and mint fee are bounded by
  signed client maxima.
- Android and iOS compatibility shims no longer send stored secrets. Their old
  mutation method fails closed; only a caller-supplied signed transaction
  envelope can reach `/api/v1/tx/send`.
- Historical pledge migration remains separately versioned. Its credential
  lookup contract is intentionally unchanged and is not accepted as a fallback
  for V2 financial execution.
- Every React Native signing entry point uses one approval boundary. The OS may
  offer its enrolled device passcode inside that same system prompt. Explicit
  cancel, denial, lockout, expiry, or an account change fails closed; the app
  does not retry with an application PIN or other weaker fallback. Signing key
  retrieval happens only after approval and the post-prompt account check.

## Mobile SDK identity and storage compatibility

The historical JavaScript Mobile SDK and canonical Wallet V1 do not hash the
compressed public key in the same way:

| Version | Input to SHA256 / RIPEMD160 | Purpose |
|---|---|---|
| `mobile_sdk_hex_text_v1` | UTF-8 public-key hex, then UTF-8 SHA256 hex | Restore an already stored historical Mobile SDK identity only |
| `wallet_v1_pubkey_hash160_v2` | Compressed public-key bytes, then raw SHA256 digest | New enrollment and canonical Wallet V1 |

For the synthetic BIP39 vector `abandon` x11 + `about`, v1 produces
`THR7BBE7B233ED012758E8C1A7281AA805D26177F66`; v2 produces
`THR3A2D4145A4F098523B3E8127F1DA87CFC55B8E79`. The SDK stores the selected
version and never replaces an existing address merely because another version
derives a different value. An address outside both vectors requires an
independently authoritative validation callback before binding.

New mnemonic persistence requires a caller-provided OS Keychain/Keystore key
provider. `default-device-key` is rejected. Unversioned historical ciphertext
is not decrypted during normal signing. Its opt-in migration requires the old
device key, successful mnemonic validation, stored-address derivation matching,
an affirmative recovery-validation callback, and a working OS-backed v2 key.
No old value is deleted or rewritten until every check succeeds.

The standalone SDK also requires a caller-provided system device authenticator
before signing or recovery export. Cancellation produces no key access and no
network call.

## Legacy SDK test-debt classification

The former 31 failures were stale expectations in one pre-client-side-wallet
test file:

- **Obsolete unsafe contract:** server-generated wallet secrets, raw
  address/secret import, predictable network encryption keys, HMAC message
  signing, secret export, and remote signature verification.
- **Historical compatibility contract:** address persistence, mnemonic import,
  export/recovery, disconnect, QR and lifecycle behavior. These are retained
  with versioned golden vectors and device-approval tests.
- **Genuine runtime regression:** the unversioned address derivation change and
  predictable default encryption key. Both are corrected by this PR.
- **Missing environment/dependency:** the old AsyncStorage mock omitted the
  module's default export and its CryptoJS mock omitted hash/encoding APIs. The
  replacement suite uses the real cryptography with an in-memory storage
  adapter.

## Rollout and rollback

1. Merge only after `#963`, `#964`, `#965`, and `#966` in that order, refreshing
   this branch after each dependency.
2. Run the Wallet V1 CI gate, mobile TypeScript check, SDK security test, and
   isolated shared-Redis replay test at the final merge SHA.
3. Produce signed Android and iOS staging builds. Verify recovery, address
   preservation, biometric cancellation, account switching, session expiry,
   offline/update behavior, and every enabled action on real devices.
4. Keep all NO-GO actions disabled. Enabling one requires its own reviewed V2
   server contract and synthetic ledger conservation tests.
5. Roll back the mobile release through the app distribution channel if a
   staging-approved action fails. Do not roll back server verification to a
   weaker legacy contract; keep the action disabled instead.

No production deployment, credential migration, live signing, financial
execution, or Railway variable change is authorized by this document.
