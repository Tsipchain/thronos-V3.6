# Thronos Chain - Testing & QA Checklist

**Version:** 1.0
**Last Updated:** 2026-01-03
**Purpose:** Prevent regressions and ensure quality before deploying changes

---

## 🚨 **CRITICAL RULE**

**NEVER deploy changes without running this checklist first!**

Before ANY commit that touches wallet, navigation, or core UI:
1. Run local testing (checklist below)
2. Verify in browser DevTools console (0 errors)
3. Test on at least 2 pages (index + one other)
4. If unsure, ask for human review

---

## 📋 **Pre-Commit Testing Checklist**

### **1. Wallet Connection Flow** ✅

#### First-Time User Flow:
- [ ] Click "Connect" button → Modal opens immediately
- [ ] Modal shows: Address field, Seed field, PIN field
- [ ] Fill all fields → Click "Connect"
- [ ] Modal closes
- [ ] Wallet popup opens automatically
- [ ] Button text changes to short address (e.g., "THR79c...301a")
- [ ] Wallet balance displays correctly

#### Returning User Flow:
- [ ] Refresh page
- [ ] Click wallet button (now shows address)
- [ ] Wallet popup toggles open/close
- [ ] Balance loads within 2 seconds
- [ ] Tokens list shows with logos

#### PIN-Only Re-Login:
- [ ] Clear localStorage
- [ ] Set address + seed in localStorage manually
- [ ] Click "Connect"
- [ ] Modal shows ONLY PIN field (address/seed hidden)
- [ ] Enter PIN → Connects successfully

---

### **2. Wallet Popup Functionality** ✅

- [ ] Popup appears below the wallet button
- [ ] Shows wallet balance (THR amount)
- [ ] Lists all tokens with:
  - [ ] Token symbol
  - [ ] Token logo/icon
  - [ ] Token balance
  - [ ] USD value (if available)
- [ ] Clicking token opens Token Info Modal
- [ ] Send button opens Send Modal
- [ ] Receive button opens Receive Modal
- [ ] Download Miner Kit button visible and functional
- [ ] Disconnect button works
- [ ] Clicking outside popup closes it

---

### **3. Token Info Modal** ✅

- [ ] Click any token in wallet popup
- [ ] Token Info Modal opens
- [ ] Shows:
  - [ ] Token name and symbol
  - [ ] Token balance
  - [ ] Token stats (supply, holders, etc.)
  - [ ] Token properties (transferable, burnable, etc.)
  - [ ] Creator address
- [ ] Close button (X) works
- [ ] Click outside modal closes it

---

### **4. Send Modal** ✅

- [ ] Click "Send" button in wallet
- [ ] Modal opens
- [ ] Network selector shows (Thronos Chain selected)
- [ ] Token dropdown shows all available tokens
- [ ] Recipient address field accepts input
- [ ] Amount field accepts numbers
- [ ] MAX button fills maximum available balance
- [ ] Speed selector (Slow/Fast) works
- [ ] Send button triggers transaction
- [ ] Success/error message displays
- [ ] Modal auto-closes on success

---

### **5. Receive Modal** ✅

- [ ] Click "Receive" button
- [ ] Modal opens
- [ ] Shows wallet address
- [ ] QR code displays
- [ ] Copy address button works
- [ ] Audio download link works
- [ ] Close button works

---

### **6. Navigation & Dropdowns** ✅

#### Desktop:
- [ ] Hover over "Apps" → Dropdown appears
- [ ] Hover over "Services" → Dropdown appears
- [ ] Hover over "Docs" → Dropdown appears
- [ ] Dropdowns stay visible while hovering
- [ ] Dropdowns close when mouse leaves

#### Mobile/Touch:
- [ ] Click "Apps" → Dropdown toggles
- [ ] Click outside → Dropdown closes
- [ ] Click another dropdown → Previous closes, new opens

#### Z-Index Issues:
- [ ] Dropdowns appear ABOVE page content
- [ ] No content blocks dropdown interaction
- [ ] Hero section doesn't overlap navbar

---

### **7. Disconnect Wallet** ✅

- [ ] Click "Disconnect" button
- [ ] Confirmation dialog appears
- [ ] Click "OK"
- [ ] Wallet popup closes
- [ ] Button text returns to "Connect"
- [ ] localStorage cleared (verify in DevTools)
- [ ] Refresh page → Still disconnected

---

### **8. Cross-Tab Synchronization** ✅

- [ ] Open site in 2 browser tabs
- [ ] Connect wallet in Tab 1
- [ ] Tab 2 automatically updates (button shows address)
- [ ] Disconnect in Tab 1
- [ ] Tab 2 automatically updates (button shows "Connect")

---

### **9. Miner Kit Download** ✅

- [ ] Connect wallet
- [ ] Open wallet popup
- [ ] "Download Miner Kit" button visible
- [ ] Click button
- [ ] Download starts OR alert if unavailable
- [ ] Button shows success message briefly

---

### **10. API Endpoints** ✅

Test these endpoints return valid JSON:
- [ ] `/api/bridge/status` → Returns: {ok, mode, last_sync, reserves, notes}
- [ ] `/api/wallet/tokens/{address}` → Returns wallet balances
- [ ] `/api/network_stats` → Returns network statistics
- [ ] `/api/tokens/list` → Returns available tokens

---

### **11. Console Errors** 🚨 **CRITICAL**

Open Browser DevTools → Console Tab:
- [ ] **0 errors on page load**
- [ ] **0 errors when connecting wallet**
- [ ] **0 errors when opening modals**
- [ ] **0 errors when navigating**

**Common errors to watch for:**
- `walletSession is not defined`
- `Cannot read property 'style' of null`
- `getElementById(...) is null`
- `Failed to fetch`
- `Uncaught ReferenceError`

---

### **12. Multi-Page Testing** ✅

Test wallet functionality on these pages:
- [ ] `/` (Index/Home)
- [ ] `/wallet` (Wallet page)
- [ ] `/swap` (Swap page)
- [ ] `/pools` (Pools page)
- [ ] `/bridge` (Bridge page)
- [ ] `/roadmap` (Roadmap page)

On each page verify:
- [ ] Wallet button works
- [ ] Popup displays correctly
- [ ] No JavaScript errors

---

### **13. Language Switching** ✅

- [ ] Click language toggle (GR/EN/etc.)
- [ ] All text updates to selected language
- [ ] Wallet modal text changes
- [ ] Wallet popup text changes
- [ ] Modals text changes
- [ ] Refresh page → Language persists

---

## 🔥 **Regression Testing (After Wallet Changes)**

If you modified wallet-related code, test these specifically:

### Modified `base.html`:
- [ ] Check all wallet functions still work
- [ ] Verify no missing elements (IDs, classes)
- [ ] Check CSS rules didn't break layout

### Modified `wallet_session.js`:
- [ ] Test all session operations
- [ ] Verify localStorage keys unchanged
- [ ] Test PIN validation

### Modified JavaScript functions:
- [ ] Test the specific function changed
- [ ] Test all functions that CALL the changed function
- [ ] Test all functions that are CALLED BY the changed function

---

## 🛠️ **Development Best Practices**

### Before Making Changes:
1. **Document current behavior** (screenshot or video)
2. **List elements being modified** (IDs, classes, functions)
3. **Identify dependencies** (what calls this? what does this call?)

### While Making Changes:
1. **One logical change at a time** (don't fix 5 things in 1 commit)
2. **Keep related code together** (modal HTML + modal JS in same commit)
3. **Comment complex logic** (why, not what)

### After Making Changes:
1. **Run this full checklist** ✅
2. **Test in browser console** (0 errors)
3. **Test on multiple pages** (index + wallet minimum)
4. **Git diff review** (did you delete something important?)

---

## 🚀 **Deployment Checklist**

### Pre-Deployment:
- [ ] All tests above passed locally
- [ ] No console errors
- [ ] Git diff reviewed (no accidental deletions)
- [ ] Commit message describes changes clearly

### Post-Deployment (Railway):
- [ ] Visit live site: https://thrchain.up.railway.app/
- [ ] Open DevTools console
- [ ] Click "Connect" → Works?
- [ ] Open wallet popup → Tokens load?
- [ ] Click a token → Modal opens?
- [ ] Check console → 0 errors?
- [ ] If any test fails → **ROLLBACK IMMEDIATELY**

---

## 🔙 **Rollback Procedure**

If live site is broken after deployment:

### Immediate Action:
```bash
# 1. Revert to last working commit
git log --oneline -10  # Find last working commit hash
git revert <commit-hash>
git push origin <branch-name>

# 2. Or reset hard (if safe)
git reset --hard <last-working-commit>
git push --force origin <branch-name>  # DANGER: Only if you're sure!

# 3. Railway auto-deploys on push, wait 2-3 minutes
# 4. Verify site works again
```

### Investigation:
```bash
# Compare working vs broken versions
git diff <working-commit> <broken-commit>

# Review what changed
git show <broken-commit>

# Check specific file changes
git diff <working> <broken> -- path/to/file.html
```

---

## 📊 **Testing Matrix**

| Feature | Index | Wallet | Swap | Bridge | Pass? |
|---------|-------|--------|------|--------|-------|
| Connect Wallet | ✅ | ✅ | ✅ | ✅ | ✅ |
| Open Popup | ✅ | ✅ | ✅ | ✅ | ✅ |
| Load Tokens | ✅ | ✅ | ✅ | ✅ | ✅ |
| Token Info | ✅ | ✅ | ✅ | ✅ | ✅ |
| Send Modal | ✅ | ✅ | ✅ | ✅ | ✅ |
| Receive Modal | ✅ | ✅ | ✅ | ✅ | ✅ |
| Disconnect | ✅ | ✅ | ✅ | ✅ | ✅ |
| Nav Dropdowns | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 🤖 **Automated Testing (Future)**

Consider implementing:
- [ ] Playwright/Cypress E2E tests
- [ ] Jest unit tests for JavaScript functions
- [ ] CI/CD pipeline with automated testing
- [ ] Visual regression testing (Percy, Chromatic)
- [ ] Lighthouse CI for performance

---

## 📝 **Change Log Template**

When committing changes, include:

```markdown
## What Changed
- Modified X function to do Y
- Added Z element to handle Q

## Why
- Previous implementation caused P problem
- User reported issue with R

## Testing Done
- ✅ Ran full checklist
- ✅ Tested on index, wallet, swap pages
- ✅ 0 console errors
- ✅ All wallet flows work

## Rollback Plan
- Revert commit <hash> if issues arise
- Specific functions to check: X(), Y(), Z()
```

---

## 🎯 **Success Criteria**

A deployment is successful when:
1. **0 JavaScript errors** in console
2. **All core flows work** (connect, popup, send, receive)
3. **Multi-page tested** (at least 3 pages)
4. **No user-reported bugs** within 24 hours

---

**Remember:** It's better to spend 10 minutes testing than 2 hours debugging a broken production site! 🚀
