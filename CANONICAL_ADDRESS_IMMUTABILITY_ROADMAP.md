# Canonical Address Immutability Fix - 3 PR Roadmap

## Executive Summary

Three focused PRs to freeze canonical wallet identity across the Thronos wallet ecosystem:

1. **PR #619: Server Identity Lock** ← Critical security boundary
2. **PR #620: Frontend Route Guard** ← UI protection layer  
3. **PR #621: Shared State Machine Contract** ← Ecosystem consistency

**Merge Order**: MUST be #619 → #620 → #621 (server-first defense)

---

## PR #619: SERVER IDENTITY LOCK

**Purpose**: Pledge endpoint cannot create new canonical if one already exists

**Tests** (5 required):
```
✓ test_pledge_does_not_create_new_if_canonical_exists
✓ test_wallet_activate_preserves_existing_thr_address  
✓ test_wallet_profile_returns_same_thr_address_after_repeat_pledge
✓ test_canonical_v1_address_field_is_immutable_once_set
✓ test_force_new_requires_explicit_confirmation_token
```

**Payload Schema** (frozen):
```json
{
  "canonical_v1_address": "THR...",
  "created": false,
  "status": "already_has_canonical",
  "signing_material_returned": true
}
```

---

## PR #620: FRONTEND ROUTE GUARD

**Purpose**: UI cannot reach create mode if canonical exists, no /pledge navigation for import/restore

**Tests** (4 required):
```
✓ test_production_dropdown_hides_restore_and_migrate_early
✓ test_create_mode_blocked_when_canonical_exists_even_if_selected_programmatically
✓ test_import_restore_never_navigates_to_pledge_when_canonical_present
✓ test_missing_canonical_shows_single_go_pledge_cta
```

---

## PR #621: SHARED STATE MACHINE CONTRACT

**Purpose**: All wallet implementations use identical state machine

**Modes**:
- `unlock`: Normal wallet operation
- `restore_recovery_kit`: Unlock existing canonical from recovery kit
- `import_signing_key`: Bind new signer to canonical
- `mirage_legacy`: Explicit opt-in legacy migration
- `pledge_new`: Create canonical (first time only)

**Tests** (3 core):
```
✓ test_state_machine_modes_are_canonical
✓ test_response_schema_consistent_across_all_clients
✓ test_canonical_immutability_rule_documented
```

---

## Current Test Status

```
✓ 10 Canonical Address Immutability tests (foundational + strict)
✓ 5 Server Identity Lock tests (PR #619) 
✓ 4 Frontend Route Guard tests (PR #620 - from hotfix)

Total: 19 tests → FROZEN canonical immutability
```

Next: Implement PR #619 with server-side enforcement
