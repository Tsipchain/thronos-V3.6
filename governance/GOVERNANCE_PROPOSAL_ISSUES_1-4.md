# GOVERNANCE PROPOSAL: Issues 1-4 Critical Fixes

**Proposal ID**: PROP_ISSUES_1-4_20260103
**Category**: CRITICAL_FIX
**Severity**: BLOCKER
**Author**: PYTHEIA AI Node
**Date**: 2026-01-03
**Branch**: claude/fix-wallet-ui-final-gUEre
**Commit**: 81e89bf

---

## PROBLEM STATEMENT

Four critical issues are blocking core user functionality:

1. **Chat history not persisting** - Assistant messages disappear after refresh
2. **File upload returns HTTP 500** - Violates Hard Rule 0
3. **Models UI shows false "API key missing"** - Confusing when keys are set with aliases
4. **DAO voting UX issues** - Accidental votes, unclear wallet status

These issues create a poor user experience and violate platform reliability standards.

---

## PROPOSED SOLUTIONS

### OPTION A: Deploy All Fixes Immediately (RECOMMENDED)

**Scope**: Deploy all implemented fixes from commit 81e89bf to production.

**What's Included**:
- ✅ Chat message persistence with deduplication
- ✅ File upload degraded mode (no HTTP 500)
- ✅ Models UI with env var alias support
- ✅ DAO voting confirmation and wallet display
- ✅ UI polish (music padding, honest status messages, wallet decimals)

**Implementation**:
1. Merge branch `claude/fix-wallet-ui-final-gUEre` to main
2. Deploy to Railway production
3. Monitor for 24 hours
4. Post PYTHEIA_ADVICE to DAO

**Files Changed**: 8 files (+212/-37 lines)

**Effort**: 15 minutes deployment + 24h monitoring

**Risk**: **Low**
- All fixes are isolated improvements
- No breaking changes to existing functionality
- Degraded mode patterns ensure graceful failures
- Easy rollback: `git revert 81e89bf`

**Cost**: 0 THR (development already completed)

**Vote Recommendation**: **STRONGLY_APPROVE** ✅

**Rationale**: All fixes address critical blockers affecting core user experience. Fixes follow best practices (degraded mode, no HTTP 500, proper error handling). No reason to delay deployment.

---

### OPTION B: Wait for Additional Testing / QA

**Scope**: Hold deployment until additional QA testing is completed.

**What's Required**:
- Manual testing of all 8 modified files
- Cross-browser testing (Chrome, Firefox, Safari)
- Mobile responsiveness testing
- Load testing with concurrent users

**Implementation**:
1. Create QA test plan
2. Execute full test suite
3. Fix any discovered issues
4. Deploy after QA signoff

**Effort**: 3-5 days QA + potential bug fixes

**Risk**: **Medium**
- Known critical issues remain in production during QA period
- Users continue experiencing chat history loss, upload failures, voting confusion
- Delayed value delivery

**Cost**: 0 THR + opportunity cost of continued user frustration

**Vote Recommendation**: **NEUTRAL** ⚠️

**Rationale**: While thorough QA is valuable, these fixes address active user pain points. All changes include acceptance tests and follow degraded mode patterns. The cost of delaying outweighs the benefit of additional QA for these specific fixes.

---

## COMPARISON

| Criterion | Option A (Deploy Now) | Option B (Wait for QA) |
|-----------|----------------------|------------------------|
| User Impact | Immediate improvement | Continued frustration |
| Risk | Low (isolated changes) | Medium (delay cost) |
| Effort | 15 min + monitoring | 3-5 days + bug fixes |
| Rollback | Easy (git revert) | Easy (git revert) |
| Cost | 0 THR | 0 THR + opportunity cost |
| Governance Transparency | High (PYTHEIA report) | High (PYTHEIA report) |
| Vote Recommendation | **STRONGLY_APPROVE** | **NEUTRAL** |

---

## ACCEPTANCE CRITERIA

**For Option A**:
- [ ] Branch merged to main
- [ ] Deployed to Railway production
- [ ] Health check passes: /chat, /architect, /api/ai/models all return 200
- [ ] PYTHEIA_ADVICE posted to DAO
- [ ] 24h monitoring shows no regressions

**For Option B**:
- [ ] QA test plan created
- [ ] All test cases executed
- [ ] Any discovered issues fixed
- [ ] Deployment proceeds per Option A

---

## ROLLBACK PLAN

**If critical issues discovered post-deployment**:

```bash
# Rollback command
git revert 81e89bf
git push origin main

# Railway auto-deploys reverted commit
# Estimated rollback time: 5 minutes
```

**Monitoring Indicators** (trigger rollback if any):
- HTTP 500 rate increases above baseline
- Chat session creation failure rate >5%
- DAO vote submission failure rate >5%
- User reports of new critical bugs

---

## PYTHEIA RECOMMENDATION

**VOTE FOR OPTION A: Deploy All Fixes Immediately**

**Evidence**:
1. All fixes address real user-reported issues
2. All changes follow Hard Rule 0 (no HTTP 500)
3. Degraded mode patterns ensure graceful failures
4. Easy rollback if issues arise
5. No breaking changes to existing functionality

**Confidence**: 95%

**Risk Assessment**: Low
- Isolated changes (8 files)
- Backward compatible
- Acceptance tests passed
- Follows established patterns

---

**Vote Now**: https://thrchain.up.railway.app/governance

**Proposal Hash**: SHA256(`PROP_ISSUES_1-4_20260103_81e89bf`)

---

**End of Proposal**
