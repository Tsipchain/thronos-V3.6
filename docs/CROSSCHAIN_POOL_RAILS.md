# Thronos cross-chain liquidity rails

## Target policy

Thronos accepts liquidity visibility and deposits from multiple supported networks, but pool-funded withdrawals are intentionally narrower.

- Inbound / held liquidity: BSC USDT, Base USDC, Arbitrum USDC, plus other wallet-visible assets as separately supported.
- Pool-funded payout rails: BSC USDT and Arbitrum stablecoins.
- Base USDC remains an inbound/held rail; it is not a preferred pool payout rail.
- Direct user-to-external-wallet transfers are ordinary user-signed EVM transfers and the user pays that network's native gas.
- Pool withdrawals are system operations: Pytheia must approve against liquidity, reserve floors, limits and payout/gas-wallet health before any broadcast.

## Stablecoin contracts

- BSC USDT: `0x55d398326f99059fF775485246999027B3197955`
- Base native USDC: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- Arbitrum One native USDC: `0xaf88d065e77c8cC2239327C5EDb3A432268e5831`

Do not enable an Arbitrum USDT payout until the exact contract used by the payout signer has been independently verified and configured.

## Required Railway variable names

Public/non-secret configuration:

- `BSC_RPC_URL`
- `BSC_RPC_LOGS_URL` (dedicated provider recommended for `eth_getLogs`)
- `BASE_RPC_URL`
- `ARBITRUM_RPC_URL`
- `ARBITRUM_RPC_LOGS_URL` (optional dedicated logs endpoint)
- `BSC_USDT_CONTRACT`
- `BASE_USDC_CONTRACT`
- `ARB_USDC_CONTRACT`
- `BSC_POOL_VAULT_ADDRESS`
- `BASE_POOL_VAULT_ADDRESS`
- `ARB_POOL_VAULT_ADDRESS`
- `PYTHIA_SYSTEM_EVM_BSC_ADDRESS`
- `PYTHIA_SYSTEM_EVM_BASE_ADDRESS`
- `PYTHIA_SYSTEM_EVM_ARBITRUM_ADDRESS`
- `BSC_PAYOUT_ADDRESS`
- `ARB_PAYOUT_ADDRESS`
- `BSC_GAS_WALLET_ADDRESS`
- `ARB_GAS_WALLET_ADDRESS`
- `BSC_FEE_COLLECTOR_ADDRESS`
- `ARB_FEE_COLLECTOR_ADDRESS`

Secrets/private signing material must stay only in Railway/secure signer storage and must never be committed to this repository.

## History model

Every wallet-visible cross-chain event should have one canonical identity and one network classification:

- `chain`: `bsc`, `base`, `arbitrum`, `bitcoin`, `thronos`, etc.
- `asset`: `USDT`, `USDC`, `BTC`, `THR`, etc.
- `direction`: `in` or `out`
- `event_type`: external send, pool deposit, pool withdrawal, bridge, pledge, etc.
- `external_tx_hash`: chain transaction hash when one exists
- `internal_txid`: Thronos-side event/request id
- `status`: pending/queued/confirmed/failed

The UI must deduplicate by canonical event identity. A pool deposit must not render once from the chain history and again from the liquidity ledger as if they were two independent transfers. The liquidity ledger is accounting/audit data; the wallet history is the user-facing normalized event stream.

## THR floor invariant

The intended economic floor is a policy target, not a claim that code alone can guarantee market price.

Initial policy reference:

- `1 THR = 10 USDT` floor target
- BTC reference: `0.0001 BTC / THR`
- pledge reserves and locked liquidity must be accounted separately from withdrawable liquidity
- existing pledge locking/unlocking schedules must not be rewritten by cross-chain payout work

A production withdrawal path must fail closed if paying it would violate the configured reserve/pledge floor. Pytheia may choose a payout rail based on verified liquidity and gas availability, but it must never manufacture liquidity or report a payout before an on-chain transaction is confirmed.

## dApp / ThronosBuilder payments

The `thrconnect` / WalletConnect-style flow should present one payment request with an explicit asset and rail:

- THR payment: internal Thronos transfer and normal THR fee policy.
- External asset payment: user-signed transaction on the selected external network, with the user paying native gas unless a separately audited sponsor/relayer is active.
- A dApp must never receive a wallet private key. It requests approval; the wallet signs.

The payment result should expose both the internal request id and external transaction hash (when external), so ThronosBuilder and other services can wait for the correct finality before delivering a paid product.
