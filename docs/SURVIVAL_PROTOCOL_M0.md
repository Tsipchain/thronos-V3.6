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

M0 accepts only THR, BTC and ETH asset identifiers and applies basic
asset-specific address boundaries. It does not claim that a BTC or ETH
address is spendable, that a raw transaction is valid for an external chain,
or that a public-network fee has been paid.

The in-memory ReplayGuard rejects duplicate message IDs and repeated
sender/nonce pairs for one verifier process. A durable atomic replay ledger,
partition reconciliation, collateral reservations, transport encryption and
network submission belong to later PRs. Callers must not present a relay ACK
as chain confirmation or update a spendable balance at delivery time.

Existing Thronos consensus, wallet signing routes, tokenomics, balances and
production APIs are not imported or changed by M0. Integrating this envelope
with Wallet V1 requires a separate compatibility review covering address-key
binding, nonce semantics, smallest-unit conversion and server acceptance.
