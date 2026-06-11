# Wallet V1 State Machine Contract

**Purpose**: Frozen modes and deterministic transitions - no auto-flip, explicit state changes only.

**Related**: PR #621 (State Machine Contract), builds on PR #619-#620.1 (Immutability foundation)

---

## Frozen Modes (No Auto-Transitions)

### Mode 1: `unlock` (Primary after canonical exists)
- **Entry**: Canonical wallet exists with signing key material
- **CTA**: "Unlock Wallet V1"
- **Form**: PIN input
- **Exit**: Pin verified → wallet unlocked
- **Constraints**: Never auto-transition to Create or Pledge

### Mode 2: `restore_recovery_kit` (Recovery path when key missing)
- **Entry**: Canonical exists but signing key missing/lost
- **CTA**: "Restore Wallet from Recovery Kit"
- **Form**: Recovery kit upload + PIN
- **Exit**: Recovery kit validated → signing key restored → auto-switch to Unlock
- **Constraints**: Only available when modalState = 'active_wallet_no_key'

### Mode 3: `import_signing_key` (Bound key import)
- **Entry**: Canonical exists, bound key needed (device change scenario)
- **CTA**: "Import Matching Signing Key"
- **Form**: Key hex + PIN
- **Exit**: Key verified → switching material loaded → auto-switch to Unlock
- **Constraints**: Only available when canonical exists and signing key missing

### Mode 4: `mirage_legacy` (Legacy wallet migration - admin only)
- **Entry**: Explicit admin flag or legacy recovery flow
- **CTA**: "Verify Legacy Wallet" or "Migrate"
- **Form**: Legacy address lookup / migration UI
- **Exit**: Migration complete → wallet canonical mapped
- **Constraints**: Hidden in production mode (admin-only, requires explicit enable flag)
- **Hard Rule**: Never shown to regular users

### Mode 5: `pledge_new` (Create canonical - new users only)
- **Entry**: NO canonical exists AND no signing material
- **Prerequisite**: modalState = 'no_active_wallet'
- **CTA**: "Go to Pledge Activation"
- **Form**: Pledge activation panel → redirect to /pledge
- **Exit**: Pledge success → canonical created
- **Constraints**: FORBIDDEN if canonical exists (immutability)
- **Hard Rule**: createAllowed = !hasCanonical() && (allowWebCreate || hasPledge)

---

## Hard Rules (Non-Negotiable)

### Rule 1: Canonical Immutability
```
IF hasCanonical() === true:
  ├─ pledge_new mode FORBIDDEN
  ├─ Create CTA button HIDDEN
  ├─ Create option DISABLED in dropdown (or removed)
  ├─ Dropdown shows ONLY: [Unlock, Restore Kit, Import Key] (+ admin options if enabled)
  └─ NO redirect to /pledge ever happens
```

### Rule 2: No Auto-Navigation to Pledge
```
IF restore/import/unlock succeeds:
  ├─ DO call refreshWalletStateFromServer()
  ├─ DO call switchWalletV1Mode() with server state
  └─ NEVER redirect to /pledge (even if modalState stale initially)
```

### Rule 3: Explicit State Selection
```
User selects mode from dropdown → UI shows that mode
IF user tries devtools hack (modeSelect.value = 'create' when canonical exists):
  ├─ switchWalletV1Mode() detects this
  ├─ Hard override: displayMode = 'unlock'
  └─ Modal state in UI doesn't match dropdown (correct behavior - displays real mode)
```

### Rule 4: Mirage Legacy Hidden (Admin-Only)
```
IF production mode (default):
  ├─ Mirage/Legacy options HIDDEN
  ├─ Restore option (legacy migration) HIDDEN
  └─ ONLY shown if WALLET_V1_LEGACY_REPAIR_UI_ENABLED = true
```

### Rule 5: Server-First State Determination
```
switchWalletV1Mode() decision tree:
  1. Get server modal_state from window.walletV1LastStatus (server truth)
  2. Use localStorage canonical detection (all key variants)
  3. If server says 'no_active_wallet' AND hasCanonical() true:
     └─ Force displayMode = 'unlock' (not 'create' or 'pledge')
  4. If client had stale state, server state wins
```

---

## State Transition Diagram

```
                    ┌─────────────────────────────────────────┐
                    │ START: App Load / Page Reload           │
                    └──────────────┬──────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │ Check: hasCanonical()?      │
                    └──────────────┬──────────────┘
                          ┌────────┴────────┐
                    YES ┌─▼────┐       NO┌──▼──┐
                       │      │         │     │
         ┌─────────────▼──┐   │   ┌─────▼──────────────┐
         │ Canonical      │   │   │ No Canonical       │
         │ Exists         │   │   │ (New User)         │
         └────┬───────────┘   │   └─────┬──────────────┘
              │               │         │
         ┌────▼─────────────┐ │    ┌────▼──────────────┐
         │ Check: Has Key?  │ │    │ Show Pledge Panel │
         └────┬─────────────┘ │    │ (pledge_new mode)│
         ┌────┴────────┐      │    └─────────────────┘
    YES │             │ NO    │
   ┌────▼────┐   ┌────▼──────┐
   │ Unlock  │   │ Restore   │
   │ (sign   │   │ Recovery  │
   │  ready) │   │ Kit       │
   └─────────┘   │ (missing  │
                 │  key)     │
                 └───────────┘
                 (or Import Key)

All modes: FROZEN
  - No auto-transition
  - No auto-flip to pledge
  - Explicit mode selection only
  - Hard override if user tries devtools hack
```

---

## Code Locations (Reference)

| Component | File | Line | Role |
|-----------|------|------|------|
| **hasCanonical()** | templates/base.html | 2700 | Detects canonical from any key |
| **switchWalletV1Mode()** | templates/base.html | 6300-6470 | Determines displayMode + availability |
| **createAllowed** | templates/base.html | 6337 | Gate: `!hasCanonical() && ...` |
| **pledgePanel visibility** | templates/base.html | 6516 | Gate: `!hasCanonical()` check |
| **Recovery Kit restore** | templates/base.html | 3431 | Sets wallet_v1_canonical_address |
| **Import signing key** | templates/base.html | 7208 | Calls refreshWalletStateFromServer |
| **refreshWalletStateFromServer** | templates/base.html | 2704 | Prevents stale modal_state |

---

## Validation Checklist

### Before Merging PR #621

- [ ] All 4 regression tests PASS (see test_pr_621_state_machine_contract.py)
- [ ] No mode auto-transitions observed (modes frozen)
- [ ] Pledge panel hidden when canonical exists
- [ ] Create option disabled in dropdown when canonical exists
- [ ] CTA text matches selected mode
- [ ] No ReferenceError in console
- [ ] Network: zero /pledge requests when canonical present
- [ ] Restore/import success: no redirect to /pledge

### Before Production Deploy

- [ ] Manual QA: Scenario A/B/C all PASS
- [ ] Production health check shows correct commit
- [ ] localStorage migration working (legacy key → canonical key)

---

## Future Considerations

1. **Pause Button UX**: Consider explicit "pause" state to prevent accidental mode exit
2. **Mode Confirmation**: Show user what mode they're in + allow one-click switch
3. **Analytics**: Track mode transitions to detect unexpected auto-flips in production
4. **Mobile**: Test mode selection on small screens

---

**Session**: https://claude.ai/code/session_01NaqX5NN9yVWWWEFN7kiTce
