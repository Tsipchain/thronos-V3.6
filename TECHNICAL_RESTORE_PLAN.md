# Technical Restore Plan

## Pledge Access Model

Whitelisted legacy/grandfathered wallets are treated as a **virtual BTC pledge** via
`effective_pledge_ok = pledge_ok || is_whitelist_legacy`. This effective flag is the
single source of truth for wallet permissions (mining, sends, bridge, music, recovery,
modules) and replaces direct pledge-only checks.
