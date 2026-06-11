# Hotfix #622 - Code Locations & Verification Points

**Purpose**: If Scenario A fails (canonical exists but /pledge still triggered), use this guide to locate exact code that needs patching.

---

## Production Crash Fix (Already Deployed)

### Location 1: advancedImportForm Declaration
**File**: `templates/base.html`  
**Line**: 6024  
**Status**: ✅ FIXED

```javascript
// Line 6024 - CORRECT (should exist)
const advancedImportForm = document.getElementById('walletV1AdvancedImportForm');

// Line 6035 - Uses the declared variable safely
if (advancedImportForm) { advancedImportForm.style.display = 'none'; hiddenLegacyElements++; }
```

**Verification**:
- [ ] Open DevTools Console (F12)
- [ ] Type: `advancedImportForm` (should NOT show ReferenceError)
- [ ] Should return DOM element or undefined (not error)

---

## Canonical Immutability Enforcement

### Location 2: hasCanonical() Function
**File**: `templates/base.html`  
**Line**: 2699  
**Status**: ✅ CORRECT

```javascript
// Line 2699 - Function definition
function hasCanonical() {
    const canonical = localStorage.getItem('wallet_v1_canonical_address');
    return canonical && canonical.startsWith('THR') && canonical.length > 10;
}
```

**Verification**:
```javascript
// In browser console:
hasCanonical()  // Should return true/false
```

---

### Location 3: Pledge Button Guard
**File**: `templates/base.html`  
**Line**: 1604  
**Status**: ✅ GUARDED

```html
<!-- Line 1604 - Should have hasCanonical() guard -->
<button onclick="
    if(hasCanonical()) { 
        alert('❌ Canonical wallet already exists...'); 
    } else if(window.location.pathname === '/pledge') {
        document.getElementById('pledgeActivationPanel').scrollIntoView();
    } else {
        window.location.href='/pledge';
    }
">Go to Pledge Activation</button>
```

**Expected Behavior**:
- If canonical exists → Alert shown, NO redirect ✅
- If on /pledge → Scroll to form, NO self-redirect ✅
- If canonical missing & not on /pledge → Redirect to /pledge ✅

**Verification Steps**:
```javascript
// Test 1: Canonical exists
localStorage.setItem('wallet_v1_canonical_address', 'THRtest1234567890');
// Click pledge button → Should show alert, NOT redirect

// Test 2: Canonical missing, on /pledge
localStorage.removeItem('wallet_v1_canonical_address');
location.href = '/pledge';
// Click button → Should scroll, NOT reload page

// Test 3: Canonical missing, not on /pledge
location.href = '/wallet';
// Click button → Should redirect to /pledge
```

---

### Location 4: Create Mode Gate
**File**: `templates/base.html`  
**Line**: 6337  
**Status**: ✅ GUARDED

```javascript
// Line 6337 - CRITICAL guard
const createAllowed = !hasCanonical() && (allowWebCreate || hasPledge);
```

**Expected Behavior**:
- If canonical exists → createAllowed = false ✅
- Create mode hidden/disabled in UI ✅

**Verification**:
```javascript
// In browser console:
localStorage.setItem('wallet_v1_canonical_address', 'THRtest1234567890');
// Call switchWalletV1Mode() - should NOT show create mode
```

---

### Location 5: Pledge Panel Visibility
**File**: `templates/base.html`  
**Line**: 6516  
**Status**: ✅ GUARDED

```javascript
// Line 6516 - Show/hide pledge panel
if (isProductionMode && modalState === 'no_active_wallet' && !hasCanonical()) {
    pledgePanel.style.display = 'block';  // Show pledge CTA
} else {
    pledgePanel.style.display = 'none';   // Hide pledge CTA
}
```

**Expected Behavior**:
- Canonical exists → Pledge panel HIDDEN ✅
- Canonical missing + no wallet → Pledge panel VISIBLE ✅

---

### Location 6: Mode Switch Function
**File**: `templates/base.html`  
**Line**: 6300-6470  
**Status**: ✅ CORRECT

Key logic points:

| Line | Behavior | Expected |
|------|----------|----------|
| 6324-6328 | Uses server modal_state if available | ✅ Server truth preferred |
| 6337 | createAllowed = !hasCanonical() && ... | ✅ Create blocked when canonical exists |
| 6438-6443 | Force unlock mode if user tried 'create' with canonical | ✅ Override devtools hacks |
| 6516 | Pledge panel visible only if !hasCanonical() | ✅ Guard in place |

---

## Import/Restore Handlers

### Location 7: Restore Handler
**File**: `templates/base.html`  
**Line**: 3464-3468  
**Status**: ✅ CORRECT

```javascript
// Line 3464-3468 - Restore completion
if (typeof refreshWalletStateFromServer === 'function') {
    await refreshWalletStateFromServer(canonical);
}
if (typeof switchWalletV1Mode === 'function') {
    switchWalletV1Mode();  // Now uses server truth
}
```

**Expected Behavior**:
- After restore, GET /api/wallet/v1/status called ✅
- Mode switches based on server state (not client state) ✅
- NO redirect to /pledge ✅

---

### Location 8: Import Handler
**File**: `templates/base.html`  
**Line**: 7205-7210  
**Status**: ✅ CORRECT

```javascript
// Line 7205-7210 - Import completion
const canonical = localStorage.getItem('wallet_v1_canonical_address');
if (canonical) {
    await refreshWalletStateFromServer(canonical);
}
switchWalletV1Mode();  // Now uses server truth
```

**Expected Behavior**:
- After import, state refreshed from server ✅
- Mode switches correctly ✅
- NO redirect to /pledge ✅

---

## Navigation Links (Acceptable)

These are **NOT** problematic - they're nav links in menus:

**Location 9a**: Line 2345
```html
<a href="/pledge">🔥 Pledge</a>
```
Status: ✅ ACCEPTABLE (navigation link, not automatic redirect)

**Location 9b**: Line 3106
```html
<a href="/pledge" class="wallet-quick-btn"></a>
```
Status: ✅ ACCEPTABLE (navigation link)

---

## If Scenario A Fails (Still Triggers /pledge)

Follow this checklist to locate the exact problem:

### Step 1: Verify hasCanonical() is working
```javascript
// In console with canonical set:
localStorage.setItem('wallet_v1_canonical_address', 'THRtest1234567890');
hasCanonical()  // Should return TRUE, not error

// If error → Line 2699 has issue
// If returns false → Check localStorage.setItem worked
```

### Step 2: Check pledge button guard
```javascript
// Open DevTools Network tab
// Click "Go to Pledge Activation" button
// Look for /pledge request

// If /pledge request appears → Line 1604 guard not working
// Check: Does onclick have hasCanonical() check?
```

### Step 3: Check switchWalletV1Mode shows correct mode
```javascript
// Call manually:
switchWalletV1Mode()

// Check what mode displays (F12 Inspector):
// If displayMode === 'unlock' → Correct ✅
// If displayMode === 'create' → Bug at line 6337-6443
// If displayMode === 'restore' → Might be correct (depends on modalState)
```

### Step 4: Check server state refresh
```javascript
// In Network tab, filter: /api/wallet/v1/status
// Trigger restore or import

// If GET /api/wallet/v1/status NOT called → Bug at line 7208 or 3465
// If called but response has wrong modal_state → Server issue, not client
```

---

## Code Patches (If Issues Found)

### IF Line 1604 pledge button doesn't guard with hasCanonical()

**Problem**: Button redirects to /pledge even when canonical exists

**Fix**:
```javascript
// OLD (vulnerable):
onclick="window.location.href='/pledge';"

// NEW (safe):
onclick="if(hasCanonical()) { 
    alert('Canonical wallet already exists'); 
} else if(window.location.pathname === '/pledge') { 
    document.getElementById('pledgeForm').scrollIntoView(); 
} else { 
    window.location.href='/pledge'; 
}"
```

**File**: `templates/base.html` line 1604  
**Patch size**: 3 lines → 8 lines

---

### IF Line 6337 createAllowed not guarded

**Problem**: Create mode enabled even with canonical

**Fix**:
```javascript
// OLD:
const createAllowed = allowWebCreate || hasPledge;

// NEW:
const createAllowed = !hasCanonical() && (allowWebCreate || hasPledge);
```

**File**: `templates/base.html` line 6337  
**Patch size**: 1 line change

---

### IF Line 6516 pledge panel not guarded

**Problem**: Pledge panel shows even with canonical

**Fix**:
```javascript
// OLD:
if (isProductionMode && modalState === 'no_active_wallet') {
    pledgePanel.style.display = 'block';
}

// NEW:
if (isProductionMode && modalState === 'no_active_wallet' && !hasCanonical()) {
    pledgePanel.style.display = 'block';
}
```

**File**: `templates/base.html` line 6516  
**Patch size**: 1 line (add `&& !hasCanonical()`)

---

### IF Line 3465 or 7208 refresh not called

**Problem**: Modal state stale after restore/import, might redirect to pledge

**Fix**:
```javascript
// OLD (missing refresh):
switchWalletV1Mode();

// NEW (with refresh):
if (canonical) {
    await refreshWalletStateFromServer(canonical);
}
switchWalletV1Mode();
```

**File**: `templates/base.html` 
- Line 3465 (restore handler)
- Line 7208 (import handler)

**Patch size**: 3-4 lines added

---

## Summary Table

| Item | File | Line | Current Status | Critical? |
|------|------|------|---|---|
| advancedImportForm declaration | base.html | 6024 | ✅ FIXED | Yes |
| hasCanonical() function | base.html | 2699 | ✅ PRESENT | Yes |
| Pledge button guard | base.html | 1604 | ✅ GUARDED | Yes |
| Create mode gate | base.html | 6337 | ✅ GUARDED | Yes |
| Pledge panel guard | base.html | 6516 | ✅ GUARDED | Yes |
| Mode switch logic | base.html | 6300-6470 | ✅ CORRECT | Yes |
| Restore state refresh | base.html | 3465 | ✅ CALLED | Yes |
| Import state refresh | base.html | 7208 | ✅ CALLED | Yes |

---

## Verification Checklist

- [ ] hasCanonical() returns correct value
- [ ] Pledge button has hasCanonical() guard
- [ ] No /pledge request when canonical exists
- [ ] No ReferenceError in console
- [ ] Create mode disabled when canonical loaded
- [ ] Pledge panel hidden when canonical exists
- [ ] Import/Restore call refreshWalletStateFromServer
- [ ] switchWalletV1Mode() uses server modal_state
- [ ] Mode switches correctly after restore/import
- [ ] No /pledge redirect after restore/import with canonical

**If all ✅**: Production is correct  
**If any ❌**: Use locations above to identify exact issue and patch

---

**Session**: https://claude.ai/code/session_01NaqX5NN9yVWWWEFN7kiTce
