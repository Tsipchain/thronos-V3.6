# Survival Protocol M0

M0 defines a transport-neutral signed envelope. It is a local verification
primitive, not a consensus or settlement change.

The signed body is canonical UTF-8 JSON preceded by the binary domain prefix
THRONOS/SURVIVAL/M0 and contains protocol/version, chain_id, asset_id,
sender/recipient, integer amount_units and fee_units, nonce, UUID message_id,
issued_at/expires_at, and a verified checkpoint height/block hash. The
signature is deterministic secp256k1 ECDSA DER over SHA-256 of those bytes.
The envelope carries a compressed public key and local lifecycle state; the
local lifecycle state is deliberately outside the signed body.

For THR, the sender must be the canonical Wallet V1 address derived from the
compressed signing public key (SHA-256, then RIPEMD-160, uppercase hex with
the `THR` prefix). Signing and verification both fail closed when the claimed
sender and public key do not match. An arbitrary valid signature therefore
cannot authorize a different THR identity.

The schema recognizes THR, BTC and ETH asset identifiers and applies basic
asset-specific address boundaries. M0 has a reviewed canonical key-to-address
derivation only for THR, so BTC and ETH signing/verification fail closed until
separate canonical binding profiles are defined. It does not claim that a BTC
or ETH address is spendable, that a raw transaction is valid for an external
chain, or that a public-network fee has been paid.

The in-memory ReplayGuard rejects duplicate message IDs and repeated
sender/nonce pairs for one verifier process. A durable atomic replay ledger,
partition reconciliation, collateral reservations, transport encryption and
network submission belong to later PRs. Callers must not present a relay ACK
as chain confirmation or update a spendable balance at delivery time.

Existing Thronos consensus, wallet signing routes, tokenomics, balances and
production APIs are not imported or changed by M0. M0 reuses Wallet V1's
canonical THR address derivation but does not submit to Wallet V1 or alter its
nonce, smallest-unit conversion, or server-acceptance behavior.
