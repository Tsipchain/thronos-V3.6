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

### Crash-recoverable migration states

The Mobile SDK migration journal uses these durable states:

1. `prepared`: explicit consent and recovery verification succeeded; the
   original ciphertext and public identity are copied to a recovery slot.
2. `new_record_written`: the OS-backed v2 ciphertext and version metadata were
   written, while the original recovery slot remains present.
3. `verified`: the v2 record was decrypted again, the mnemonic matched, and its
   selected derivation reproduced the exact stored address.
4. `rolled_back`: restart recovery could not verify a complete v2 record and
   restored the original address, ciphertext, and version metadata.

Restart recovery handles termination after the backup, during the v2 batch,
after the new record, and before final verification. The original encrypted
record is not automatically deleted, including after `verified`; removing it
requires a separately reviewed cleanup/retention policy.

### Historical SignedTxEnvelope authorization

`mobile_sdk_hex_text_v1` is an identity derivation compatibility label, not an
authentication bypass. Its public key derives to the canonical v2 key address,
not to the historical address. The real backend accepts that envelope only
when `wallet_v1_public_key_bindings.json` contains an active binding from the
historical address to the exact public key and canonical `public_key_address`.
Missing, revoked, unrelated, or mismatched bindings fail closed. Signature
tampering and nonce replay also fail before execution.

### Host adapter and build evidence boundary

The checked-in Expo host now supplies an OS-backed adapter using
`expo-secure-store` with `WHEN_UNLOCKED_THIS_DEVICE_ONLY` and required device
authentication, plus `expo-local-authentication` for biometric/device-passcode
approval. It never derives a key from a device identifier.

This repository snapshot has no checked-in generated Android/iOS host project,
Gradle wrapper, Xcode workspace, signing certificates, populated EAS project
ID, or EAS CLI. TypeScript and contract tests are executable here; signed APK,
AAB, and IPA evidence must therefore be produced later in the approved mobile
build environment. Standalone Kotlin/Swift compatibility shims remain NO-GO
for wallet creation or signing because they accept only caller-supplied signed
envelopes and do not implement the reviewed local signer.

The managed Expo application has an explicit internal-build profile. It uses
remote EAS credentials, produces an Android APK and a physical-device iOS
build, disables Android cleartext traffic and backup, and keeps financial
actions disabled. `EAS_PROJECT_ID` is intentionally not committed. The build
preflight rejects an absent, placeholder, or malformed project UUID before a
build request is submitted. `.easignore` excludes environment files, signing
artifacts, credentials, databases, and secret-bearing files from build upload.

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

### Operator acceptance checklist

No box below may be inferred from unit tests or a successful cloud build.

**Before build**

- [ ] Record the reviewed Git SHA and confirm the Draft dependency chain is
  `#963 -> #964 -> #965 -> #966 -> #968`.
- [ ] Authenticate the approved EAS operator and set the genuine
  `EAS_PROJECT_ID` without writing it to source control.
- [ ] Confirm EAS owns the intended `com.thronos.wallet` Android package and
  iOS bundle identifier.
- [ ] Confirm the approved remote Android keystore and Apple distribution
  certificate/provisioning profile. Never export their private material into
  repository files or CI logs.
- [ ] Run `npm run native:config:check`, TypeScript, Wallet V1, pledge, Mobile
  SDK, backend-binding, migration-fault, and shared-Redis replay gates at the
  same SHA.

**Build evidence**

- [ ] Run `npm run build:rc:android` and record the EAS build ID, artifact
  SHA-256, application ID, version/build number, Git SHA, and signer
  certificate fingerprint.
- [ ] Run `npm run build:rc:ios` and record the EAS build ID, artifact SHA-256,
  bundle ID, version/build number, Git SHA, Team ID, and provisioning profile
  identity.
- [ ] Verify both artifacts are internal-distribution builds and that no
  production financial-action flag is enabled.

**Physical-device acceptance**

- [ ] On supported Android versions, test a clean install and an upgrade over
  a copy of historical encrypted SDK storage.
- [ ] On supported iOS versions, test a clean install and an upgrade over a
  copy of historical encrypted SDK storage.
- [ ] Confirm the exact historical and canonical THR addresses, BTC/USDT
  pledge identities, recovery-kit access, read-only balances, and transaction
  history remain unchanged.
- [ ] Confirm Keychain/Keystore creation, retrieval after restart, device-only
  access, lockout, deletion only after explicit wallet removal, and absence
  from backup/restore onto another device.
- [ ] Test biometric approval, explicit cancellation, denial, lockout,
  device-passcode fallback within the same OS prompt, timeout, backgrounding,
  account switching, and signing cancellation. Cancellation must cause no key
  read and no network request.
- [ ] Exercise migration interruptions after journal creation and after new
  ciphertext write. Restart the app and prove recovery of the original record
  or verified completion without address change.
- [ ] Validate historical and canonical signer bindings against the actual
  isolated backend; reject unrelated keys, stale accounts, altered envelopes,
  duplicate nonces, and cross-instance replays.

**Release and rollback**

- [ ] Keep swaps, withdrawals, pools, staking, bridge, settlement, governance,
  token/NFT mutations, and every other non-reviewed action disabled.
- [ ] Obtain explicit operator sign-off on the build IDs and device matrix.
- [ ] Distribute only to the approved internal cohort; do not submit to public
  stores from this gate.
- [ ] If acceptance fails, stop distribution and revoke the affected internal
  build. Keep strict backend verification enabled and the affected action
  disabled; never restore a weaker legacy authorization fallback.
- [ ] For an interrupted credential migration, use the durable journal and
  preserved original encrypted record. Do not rewrite server identity,
  bindings, balances, pledge history, or transaction history.
- [ ] Preserve failed artifacts and sanitized logs for review. Do not delete
  the original encrypted record until a separately approved retention policy
  has completed verified recovery evidence.

### Evidence register for this revision

| Evidence | State |
|---|---|
| EAS operator authentication | **BLOCKED** — execution environment is not logged in |
| Genuine Expo project UUID | **BLOCKED** — not available in the execution environment |
| Android signing credentials | **BLOCKED** — not available to this review |
| Apple signing/provisioning credentials | **BLOCKED** — not available to this review |
| Android internal build ID/artifact | **NOT PRODUCED** |
| iOS internal build ID/artifact | **NOT PRODUCED** |
| Physical Android device matrix | **NOT RUN** |
| Physical iOS device matrix | **NOT RUN** |

These blocked entries are release evidence requirements, not test failures.
They must not be replaced with fabricated identifiers, simulator screenshots,
or unsigned artifacts.

## Release-candidate evidence

- Historical Mobile SDK golden mnemonic restores the exact v1 address and
  produces the reviewed SignedTxEnvelope without address conversion.
- The actual Python backend verifier accepts that envelope only with the exact
  active historical-to-canonical signer binding. Missing, revoked, wrong-key,
  modified-payload, and replay cases are rejected.
- Migration fault tests cover termination after backup, termination after the
  new record write, an interrupted AsyncStorage batch, unavailable OS key after
  restart, deterministic rollback, and successful resume.
- An isolated Redis 7 container exercised 16 concurrent independent workers;
  exactly one nonce was accepted and 15 were rejected as replay. The container
  was removed after the test. This is local staging evidence, not a production
  deployment.
- Signed mobile binaries and real-device screenshots are not evidence in this
  PR because the required native projects, signing credentials, and build
  services are unavailable in the execution environment.

No production deployment, credential migration, live signing, financial
execution, or Railway variable change is authorized by this document.
