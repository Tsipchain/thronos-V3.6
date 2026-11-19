# BTC provider revenue observer (read-only)

## Boundary

Purpose `earn_provider_revenue` watches only the corporate CPX/TimeWall mainnet
revenue address:

`1N5ddgzVp5it6FgxninDD1R56Rh72D9HKy`

It is not a pledge vault, bridge deposit address, user wallet, hot wallet,
treasury reserve, mint source, or payout reserve. The observer never credits a
balance, mints an asset, signs or broadcasts a transaction, or sends this
purpose to the BTC deposit adapter.

The address must be checked in the actual CPX and TimeWall payout dashboards
before the local watch registry is enabled. Repository configuration is not
evidence of provider configuration. Set
`BTC_PROVIDER_REVENUE_PAYOUT_CONFIG_VERIFIED=true` only after both provider
records have been inspected and retained as operator evidence.

## Reconciliation contract

Bitcoin evidence comes only from the existing PR #952 local Bitcoin Core
observer. This change reuses its RPC/ZMQ ingestion, block recovery, integer
satoshi conversion, `txid:vout` identity, confirmation tracking, and reorg
state. It does not create a second checkpoint or ZMQ consumer.

Each CPX or TimeWall statement must supply:

- `provider`: exactly `cpx` or `timewall`;
- `statement_id`: immutable provider statement/payment identifier;
- `period_ref`: provider reporting period;
- `txid` and `vout`: the explicit Bitcoin output claimed by the statement;
- `expected_sats`: positive integer satoshis.

The idempotency key is `main:txid:vout`. An identical repeated statement is
idempotent. A changed amount, provider identity, or output is a conflict.

Because both providers pay the same address, the Bitcoin input/sender address
must never be used to infer CPX versus TimeWall. A record is `matched` only when
the explicit statement matches the watched output, exact integer satoshis,
canonical block evidence, and at least six confirmations. Missing history,
observer recovery flags, conflicting data, or a reorg remains pending or under
review. Every classification transition is appended to a durable audit table.

The report command is read-only and does not create schema or touch the SQLite
WAL:

```powershell
python -m services.btc_node_agent --db $ObserverDb --provider-revenue-report
```

## Local watch registry

Create this file only on the Bitcoin Core/observer host, not Railway:

```json
{
  "1N5ddgzVp5it6FgxninDD1R56Rh72D9HKy": "earn_provider_revenue"
}
```

The loader fails closed if the address and purpose are not this exact pair or
if the provider payout verification flag is absent. Confirmed records with this
purpose are excluded from the adapter outbox even if generic deposit delivery
is later enabled.

## Windows Bitcoin Core staging checklist

These commands are non-destructive. They do not reset recovery flags, delete a
checkpoint, enable delivery, or send BTC.

1. In `bitcoin.conf`, keep RPC and ZMQ local to the Windows host. An archival
   node is recommended for historical provider reconciliation:

   ```text
   server=1
   prune=0
   txindex=1
   rpcbind=127.0.0.1
   rpcallowip=127.0.0.1
   zmqpubhashblock=tcp://127.0.0.1:28332
   zmqpubrawtx=tcp://127.0.0.1:28333
   zmqpubsequence=tcp://127.0.0.1:28334
   ```

   If the current node is pruned, do not change it in place merely to satisfy
   this checklist. Use a separately approved authenticated archival Bitcoin
   Core node for unavailable historical blocks.

2. Verify Core locally without printing RPC credentials:

   ```powershell
   bitcoin-cli -rpcconnect=127.0.0.1 getblockchaininfo
   bitcoin-cli -rpcconnect=127.0.0.1 getblockhash 0
   bitcoin-cli -rpcconnect=127.0.0.1 validateaddress 1N5ddgzVp5it6FgxninDD1R56Rh72D9HKy
   bitcoin-cli -rpcconnect=127.0.0.1 getzmqnotifications
   ```

   Required evidence: `chain=main`, initial block download false, block/header
   tips equal, genesis
   `000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f`,
   address valid, and all three loopback ZMQ topics present.

3. Capture a committed SQLite backup including WAL state with Python SQLite
   backup semantics. This does not require copying a live `-wal` file:

   ```powershell
   $ErrorActionPreference = 'Stop'
   $Repo = (Resolve-Path 'C:\path\to\thronos-V3.6').Path
   $ObserverDb = 'C:\ProgramData\Thronos\btc_observer.db'
   $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
   $BackupDir = Join-Path 'C:\ProgramData\Thronos\backups' $Stamp
   New-Item -ItemType Directory -Path $BackupDir | Out-Null
   $BackupDb = Join-Path $BackupDir 'btc_observer.db'
   Set-Location $Repo
   python -c "import sqlite3,sys; s=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" $ObserverDb $BackupDb
   Get-FileHash -Algorithm SHA256 $BackupDb
   ```

4. Inspect recovery state before adding the revenue watch:

   ```powershell
   $env:BTC_DEPOSIT_DELIVERY_ENABLED = '0'
   python -m services.btc_node_agent --db $ObserverDb --recovery-status
   ```

   Stop if history is unverified, reconciliation is required, a ZMQ gap is
   open, or the scan checkpoint is absent. Do not clear any flag.

5. After CPX and TimeWall payout dashboards have both been verified, set only
   local process variables and run preflight/probe. Do not place Core RPC
   credentials in Railway:

   ```powershell
   $env:BTC_WATCH_REGISTRY = 'C:\ProgramData\Thronos\provider-revenue-watch.json'
   $env:BTC_PROVIDER_REVENUE_PAYOUT_CONFIG_VERIFIED = 'true'
   $env:BTC_DEPOSIT_DELIVERY_ENABLED = '0'
   python -m services.btc_node_agent --db $ObserverDb --watch-registry $env:BTC_WATCH_REGISTRY --probe-zmq 10
   python -m services.btc_node_agent --db $ObserverDb --provider-revenue-report
   ```

6. Retain the recovery JSON, Core outputs, provider configuration evidence,
   statement export hashes, database backup hash, and read-only report. No live
   BTC test is authorized by this checklist.

## Production blockers

- CPX and TimeWall payout configuration has not been independently evidenced.
- PR #952 and this stacked change are Drafts and must be reviewed in order.
- Historical coverage must be complete or supplied by an authenticated
  archival Core node; public explorers are not authoritative evidence.
- Adapter persistent storage and authentication must be completed before any
  deposit delivery is considered. Revenue purpose remains non-deliverable even
  after that work.
