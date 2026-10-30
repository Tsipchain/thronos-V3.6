# Thronos Roadmap Evidence Audit

**Audit date:** 2026-10-30  
**Repository baseline:** `b4e8498435468b348f94c309543a5b909eced76c`  
**Scope:** public roadmap, core implementation paths, current Earn pilot, open safety PRs, and release gates.  
**Method:** source inspection + CI/PR evidence + live public-page inspection. A feature is not marked live merely because code, a template, a UI button, or an old document exists.

## Status vocabulary

| Label | Meaning |
|---|---|
| **Verified** | Source and current automated/manual evidence support the bounded claim. |
| **Controlled pilot** | Limited real-user testing is active; settlement and/or public rollout remains gated. |
| **Draft / hardening** | Implementation exists on a branch or needs security/operational review. |
| **Blocked** | A safety, custody, identity, or confirmation prerequisite is missing. |
| **Planned** | Product direction only; not a delivery claim. |

## Current status ledger

| Area | Evidence observed | Truthful public status | Release gate |
|---|---|---|---|
| Core chain / THR / wallet | Core source and wallet surfaces exist. | **Verified implementation surface; production assertions require separate operational evidence.** | Maintain health checks and transaction-level monitoring. |
| Earn / CPX | Earn account ledger, signed CPX postback handling and PWA activity UI are present. Pilot users have received pending receipts. | **Controlled pilot.** Pending THC is not cleared, payable, transferable, stakeable, or a cash-out balance. | Provider-confirmed clearance for each receipt; idempotent state transition; reconciliation tests. |
| Earn PWA / web link | One-time wallet-link work and PWA activity fixes were merged; PWA cache was bumped. | **Controlled pilot.** Wallet remains optional; link must never change reward state. | Cross-device acceptance matrix; signed challenge, expiry, duplicate-link and unlink/recovery tests. |
| BitcoTasks | Provider integration variables/configuration may exist, but approval and callback verification are not established in this audit. | **Blocked / provider approval pending.** | Official documentation validation, server-side identity, signed/idempotent postback tests, production approval. |
| BSC / Arbitrum asset support | Asset/network UI and watchers exist; canonical history dedupe is in draft PR #818. | **Draft hardening.** | Merge only after canonical identity is durable: numeric chain id + tx hash + log index/event id, per-wallet projection, concurrency protection, migration dry-run, CI. |
| Pool withdrawals / treasury settlement | No approved evidence of reserve verification, confirmed broadcast or idempotent settlement. | **Blocked.** | Funded and reconciled reserve, Pytheia policy check, human approval, real tx hash and confirmation, idempotency and incident runbook. |
| BTC bridge / external BTC cash-out | Safety code/audit exists, but no audited signer, funded reserve, confirmations or safe custody release evidence. | **Blocked — deposit observation is not withdrawal capability.** | Watch-only reserve, offline/multisig signer, policy state machine, human approval, broadcast + confirmations, txid storage and reconciliation. |
| AMM / swaps / liquidity | Code and UI claims exist but this audit does not establish live liquidity, solvency or safe withdrawal settlement. | **Implementation / verification required.** | On-chain reserve reconciliation, actual pool balances, price impact/slippage tests, no simulated success, release approval. |
| L2E / ThronosEdu | Course/quiz/attestation components exist. PR #20 remains draft with identity, tenant isolation, teacher-wallet and disclosure blockers. | **Draft hardening; no broad production claim.** | Resolve PR #20 security review, verified teacher wallet policy, tenant isolation, authenticated learner identity, payment webhooks before fiat enrollment. |
| Train2Earn | Product concept only; intended as a separate ThronosLabs SaaS. | **Planned.** | New repository, consent/privacy design, proof policy, independent ledger, subscription compliance and no automatic conversion/financial promises. |
| Pytheia | Monitoring/policy roles are discussed; it must not be a lone custody signer. | **Planned policy role.** | Read-only monitoring, threshold policy, human approval and separate signer architecture. |

## Explicit non-claims

The public roadmap must **not** claim any of the following as live until release evidence exists:

- automatic BTC or external-asset withdrawals;
- autonomous treasury trading, CEX API withdrawals, or unsupervised rebalancing;
- verified live pool liquidity, APY, staking or revenue share;
- cleared/payoutable Earn THC before provider clearing;
- broad L2E/ThronosEdu production rollout before identity and tenant safety gates;
- medical, financial, KYC/AML or regulatory guarantees.

## Ordered delivery plan

1. **Earn pilot reliability:** fix mobile/web activity visibility, preserve session/link UX, display only provider-backed pending/cleared states, collect pilot evidence.
2. **History integrity:** complete and review PR #818 canonical event identity; run migration in dry-run mode before any production dedupe.
3. **Wallet-link acceptance:** device matrix across web, Android PWA/APK and iOS browser; biometric/passkey gate where applicable; no reward/custody side effects.
4. **Earn clearance design:** signed provider clearance event → same receipt transitions `pending → confirmed → payable`; no timer-based clearing.
5. **BTC custody design:** separate watch-only reserve, signer, human approval and confirmation/reconciliation. No funding or payout enablement in this phase.
6. **Edu security:** resolve PR #20 blockers before guest/fiat course rollout.
7. **Provider expansion:** BitcoTasks only after official postback contract and approval; third providers follow the same integration checklist.
8. **Future services:** Train2Earn / games / ads stay separate products and ledgers until their own security, consent, accounting and legal review.

## Roadmap governance

- Every public roadmap line must map to a source file, test/CI result, deployment evidence, or a release gate.
- Labels are reviewed at least once per release; stale entries move to **Draft**, **Blocked**, or **Planned**, never silently remain “complete”.
- A public completion label for money movement requires: real transaction id, chain confirmation, durable idempotency record, reconciliation evidence and named release approval.
- Source code or a UI button alone is not production evidence.
- This document supersedes outdated completion claims only for roadmap status. It does not alter tokenomics, mining, fees, pledge economics, liquidity policy or any user balance.

## Backlog of stale public documentation

Review and reconcile, rather than rely on, these legacy sources:

- `templates/roadmap.html` (replaced by the evidence-led public board in this change);
- `Thronos_Roadmap.md`;
- `ROADMAP_2026_UPDATED.md`;
- `Thronos_Whitepaper_Full.md`;
- `WHITEPAPER_PROFESSIONAL_2026.md`;
- legacy architecture/status summaries that state completion without release evidence.

