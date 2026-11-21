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
