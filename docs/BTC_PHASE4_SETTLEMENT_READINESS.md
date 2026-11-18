# BTC Phase 4 settlement readiness

Status: read-only/default-disabled implementation review. No production credit,
delivery, payout, signer or broadcaster is enabled by this document or its
companion code.

## Dependency and merge order

The Drafts form two explicit chains:

1. Thronos observer and containment:
   - Observer #952 (`codex/btc-observer-checkpoint-closure`)
   - Legacy containment #953 (`codex/btc-phase3-legacy-credit-gate`)
   - Phase 4 Thronos accounting/custody PR (stacked on #953)
2. Adapter:
   - #5 durable authenticated receipt storage
   - #6 independent Bitcoin Core verification
   - #7 durable non-delivering settlement handoff
   - #8 purpose/version-bound integration command

#952 and #953 are both based on `main`; merge one, refresh the other against the
new `main`, and rerun both gates. The Phase 4 Thronos PR must be retargeted only
after #953 merges. Adapter PRs must merge strictly #5 -> #6 -> #7 -> #8. The
Thronos accounting PR also logically depends on the final #8 command contract.
No PR should be merged automatically.

## Bridge and Earn boundary audit

### Bridge BTC pledge eligibility

The legacy path still derives eligibility from JSON pledge/chain records through
`server.py::has_btc_pledge`. It is not canonical Bitcoin evidence. Draft #953
default-disables the public-explorer watcher and direct-credit endpoint.

The Phase 4 accounting inbox accepts `bridge_pledge_eligibility` only after an
independently verified command. It writes immutable eligibility evidence but
does not activate or unlock a wallet. A later reviewed integration must make
wallet eligibility read this evidence and must remove the legacy JSON record as
an authority.

### Verified deposits and Bridge accounting

The canonical identity is `main:txid:vout`. The accounting inbox writes one
BTC-denominated satoshi journal entry, an inbox receipt and an audit record in
one SQLite transaction. It never converts BTC to THR, THC or L2E and never
updates the existing balance ledger. Duplicate delivery returns the original
accounting receipt; a conflicting replay fails closed.

### Wallet unlock reservations

`services/earn_account.py` wallet-unlock pledges are authoritative THC
reservations with reserved/settled/released transitions. They are independent
of Bitcoin deposit settlement. Phase 4 does not change their amount, timing,
eligibility or wallet creation behavior. Canonical BTC pledge evidence must be
an input to a separately approved eligibility policy, never an implicit THC
reservation settlement.

### Earn BTC reserve and cashout

`services/pythia_btc_reserve.py` is a read-only confirmed-UTXO snapshot and is
not a payout coordinator. The Phase 4 inbound purpose
`earn_reserve_settlement` records exact satoshis only; it does not increase a
user balance or authorize withdrawals.

Existing external BTC cashout code retains its current minimum, fee bounds and
reservation transitions. Its injected verifier contract is still incomplete:
the result does not yet persist exact vout, returned destination, canonical
block identity or current confirmation depth. No production coordinator is
wired. `BtcPayoutCoordinator` is therefore an interface only; implementation
must remain separate from inbound deposits and from BridgeHot.

## Reorg and compensation policy

Before accounting, a reorg moves the adapter receipt to
`reconciliation_required` and no command is created. After a synthetic
accounting receipt, a reorg moves the adapter to `compensation_pending` and
holds the command. The downstream inbox changes its BTC journal and eligibility
evidence to `held`; it preserves the original amount and audit record. It does
not delete or rewrite history and does not create a compensating spendable
balance automatically. Human/policy approval is required for any later
economic compensation.

## Custody isolation

Required public-address roles:

| Role | Required mode | Boundary |
|---|---|---|
| BridgeHot | external signer | Bridge payouts only |
| EarnHot | external signer | Earn payouts only |
| BridgeWatch | watch-only | Deposit observation only |
| OfflineTreasury | offline | No automatic signer |
| BtcSettlementReserve | watch-only | Reserve proof only |

All five roles are distinct by default. BridgeHot, EarnHot and OfflineTreasury
can never share an address, even through an override. BridgeWatch and the
settlement reserve may share only through an explicit allow-policy and trusted
Bitcoin Core evidence that the address is watch-only. Validation rejects
non-mainnet or invalid addresses and any evidence indicating local private
keys. No private key, seed, descriptor secret or extended public key is read or
printed.

## Windows observer database recovery checklist

Use the reviewed #952 revision. Replace only the path and Windows service name.
Do not reset flags, delete checkpoints, recreate the database, enable delivery
or run the history-acknowledgement command during this inspection.

```powershell
$Repo = 'C:\Thronos\thronos-V3.6'
$Db = 'C:\Thronos\data\btc_observer.db'
$ServiceName = '<BTC_OBSERVER_WINDOWS_SERVICE_NAME>'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupDir = "C:\Thronos\backups\btc-observer-$Stamp"

Set-Location $Repo
git fetch origin
git switch codex/btc-observer-checkpoint-closure
git pull --ff-only origin codex/btc-observer-checkpoint-closure
git rev-parse HEAD

New-Item -ItemType Directory -Path $BackupDir -ErrorAction Stop | Out-Null
Stop-Service -Name $ServiceName -ErrorAction Stop
try {
    $Files = @($Db, "$Db-wal", "$Db-shm") | Where-Object { Test-Path -LiteralPath $_ }
    foreach ($File in $Files) {
        Copy-Item -LiteralPath $File -Destination $BackupDir -ErrorAction Stop
    }

    $LogicalBackup = Join-Path $BackupDir 'btc_observer.logical.db'
    & sqlite3.exe $Db ".timeout 30000" ".backup '$LogicalBackup'"
    if ($LASTEXITCODE -ne 0) { throw 'SQLite online backup failed' }
    $Integrity = & sqlite3.exe $LogicalBackup "PRAGMA integrity_check;"
    if ($LASTEXITCODE -ne 0 -or $Integrity.Trim() -ne 'ok') {
        throw "SQLite integrity check failed: $Integrity"
    }
    Get-ChildItem -LiteralPath $BackupDir | Get-FileHash -Algorithm SHA256

    python -m services.btc_node_agent --db $Db --recovery-status
    if ($LASTEXITCODE -ne 0) { throw 'Recovery-status inspection failed' }
}
finally {
    Start-Service -Name $ServiceName -ErrorAction Stop
}
```

Stopping the observer before the raw copy captures the database, WAL and SHM as
one quiescent set. SQLite `.backup` additionally produces a transactionally
consistent logical database including committed WAL content; it does not run a
checkpoint or alter recovery flags. Do not continue if `integrity_check` is not
exactly `ok` or if the reviewed head is not the expected #952 revision.

## Railway staging checklist

Provisioning requires owner approval and must use a separate staging
environment/service. Do not modify production while collecting this evidence.

1. Mount one persistent volume at `/data` on the staging adapter.
2. Use one replica while SQLite is the receipt/handoff store.
3. Set `BTC_DEPOSIT_DB_PATH=/data/btc_deposits.db`.
4. Keep adapter settlement delivery and credit disabled.
5. Use separate authenticated read-only RPC credentials for primary Bitcoin
   Core and the archival Core verifier.
6. Mount a versioned watch-registry file read-only. Do not place credentials or
   extended public keys in it.
7. Configure six or more confirmations.
8. Confirm health reports receipt storage configured while settlement delivery
   and credit both remain false.
9. Restart/redeploy and prove the receipt count, command, proof and audit persist.
10. Detach/misconfigure the volume in a disposable staging clone and confirm
    ingest fails closed rather than creating an ephemeral replacement database.

Proposed verifier variable names must not be staged until an approved runtime
factory consumes them: `BTC_VERIFY_RPC_URL`, `BTC_VERIFY_RPC_USER`,
`BTC_VERIFY_RPC_PASSWORD`, `BTC_ARCHIVAL_RPC_URL`, `BTC_ARCHIVAL_RPC_USER`,
`BTC_ARCHIVAL_RPC_PASSWORD`, and `BTC_WATCH_REGISTRY_PATH`.

## Synthetic staging evidence scenarios

| Scenario | Required outcome |
|---|---|
| Valid six-confirmation output | One canonical proof and command |
| Wrong network/genesis | Conflict; no command |
| Wrong vout/address/ScriptPubKey/satoshis | Quarantine; no command |
| Duplicate/concurrent duplicate | One receipt, proof, command and accounting entry |
| Conflicting receipt | HTTP/storage conflict; original preserved |
| Insufficient confirmations | No proof/command |
| Canonical block mismatch | No proof/command |
| Pruned primary, no archive | Verification pending |
| Pruned primary, valid authenticated archive | Canonical proof from archive |
| Reorg before command | Reconciliation required |
| Reorg after credited fixture | Compensation pending and held |
| Crash during command transaction | Full rollback; retry creates one command |
| Crash during accounting transaction | Full inbox/ledger/audit rollback |
| Database restart | Exact state and idempotent replay preserved |

## Production readiness matrix

| Component | Status | Production disposition |
|---|---|---|
| Observer ZMQ/RPC reconciliation | Implemented in Draft #952 | Merge/recovery evidence required |
| Legacy pledge containment | Implemented in Draft #953 | Must remain default-off |
| Adapter durable receipt store | Implemented in Draft #5 | Persistent volume required |
| Independent Core verifier | Implemented in Draft #6 | Runtime configuration not active |
| Durable handoff | Implemented in Draft #7 | Delivery disabled |
| Purpose-bound command | Implemented in Draft #8 | Downstream dependency |
| Atomic BTC accounting inbox | Implemented, default disabled | No production route/worker |
| Wallet eligibility evidence | Implemented, not wired | Legacy authority removal required |
| Custody isolation validation | Implemented, not wired | Operator role manifest required |
| Earn payout coordinator | Interface only | Missing/blocking |
| Cashout canonical proof contract | Incomplete | Blocking |
| Reorg automatic economic compensation | Intentionally absent | Policy/approval required |
| Real BTC deposit | Not performed | Explicit later approval required |

## Conditions for the first controlled real BTC deposit

All conditions are mandatory:

1. #952, #953, Adapter #5, #6, #7 and #8 are reviewed, merged in order and
   their final SHAs recorded.
2. The Phase 4 Thronos accounting/custody PR is reviewed and merged, but its
   consumer remains disabled until the test window.
3. Windows recovery status and all open historical/gap diagnostics are attached
   to the release record; no flag is manually cleared.
4. Adapter staging passes every scenario above across restart and volume
   persistence.
5. Primary and archival Bitcoin Core endpoints independently prove mainnet,
   genesis and retained block availability.
6. The exact watch-registry version, address, ScriptPubKey, purpose and intended
   recipient are approved without exposing extended public keys.
7. BridgeHot, EarnHot, BridgeWatch, OfflineTreasury and settlement reserve pass
   custody validation and are not aliased incompatibly.
8. Deposit delivery, accounting consumption and any acknowledgement are enabled
   only for the bounded test identity/window; withdrawals remain disabled.
9. A tiny owner-approved amount and explicit maximum loss are documented.
10. Before sending, operators record BTC and internal accounting baselines.
11. After confirmation, evidence shows exactly one `main:txid:vout` receipt,
    proof, command, inbox receipt and audit chain; replay adds zero.
12. A rollback/hold procedure and named approver are present before the send.

No real BTC should be sent until the owner explicitly approves that exact test.
