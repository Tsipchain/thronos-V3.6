# Thronos Wallet SDK (v3.8)

This document describes the stable wallet integration surface for browser extensions, mobile WebView wrappers, and companion apps.

## Global Object

`window.ThronosWallet` is available on every page via `static/wallet_sdk.js`.

### Methods
- `open(options?)` → opens/unlocks the wallet (keeps UI closed when `options.showUi === false`).
- `lock()` → locks the wallet locally (credentials remain on device).
- `unlock(options?)` → unlocks using PIN, biometric/passkey hooks, or saved session.
- `send({ token, to, amount, speed, passphrase })` → routes to `/api/wallet/send` with the current wallet credentials.
- `getHistory({ tab, limit })` → fetches `/wallet_data/<address>` and filters by tab (`all|thr|tokens|l2e|ai|iot|bridge|swaps`).
- `on(event, handler)` / `off(event, handler)` → add/remove listeners for wallet lifecycle events.

### Events
- `thronos:wallet:open`
- `thronos:wallet:lock`
- `thronos:wallet:unlock`
- `thronos:wallet:tx_status` (emitted after `send` submission)

### Hooks for Wrappers
Wrappers can inject helpers on `window.ThronosWalletHooks`:
- `biometricUnlock(): Promise<boolean>` → return `true` to approve unlock.
- Additional passkey/secure storage helpers can be wired through `walletSession.setCustomUnlockHandler(fn)` if deeper control is required.

## Lock / Unlock Behavior
- Locking sets a local lock flag and clears the `bound` session without deleting the stored address/secret.
- Unlock first tries custom unlock handlers and biometric hooks, then PIN (when set), and finally falls back to stored credentials.
- Keys never leave the device; no seed re-entry is required after the first unlock unless the device is forgotten.

## Content Script Compatibility
- All SDK methods avoid direct DOM access (UI open is optional via `showUi` flag).
- Events are standard `CustomEvent`s on `window`, compatible with extension messaging bridges.

## Mobile / WebView Notes
- Use `ThronosWalletHooks.biometricUnlock` to integrate native biometrics.
- Secure storage wrappers can persist the PIN/secret locally; the SDK never transmits them except in wallet send requests already used by the web UI.
- Passkey unlocks can be delegated to a custom handler registered through `walletSession.setCustomUnlockHandler` before calling `ThronosWallet.unlock()`.

## Smoke-Test Checklist
- [ ] Call `ThronosWallet.open()` → wallet opens/unlocks and emits `thronos:wallet:open`.
- [ ] Call `ThronosWallet.lock()` → wallet locks and emits `thronos:wallet:lock`; UI remains unchanged.
- [ ] `ThronosWallet.unlock({ pin })` → unlocks with the stored PIN and emits `thronos:wallet:unlock`.
- [ ] `ThronosWallet.send(...)` → posts to `/api/wallet/send` and emits `thronos:wallet:tx_status`.
- [ ] `ThronosWallet.getHistory({ tab: 'tokens' })` → returns filtered token transfers from `/wallet_data/<address>`.
- [ ] Content script can listen to events via `window.addEventListener(EVENT, cb)` without DOM access.
