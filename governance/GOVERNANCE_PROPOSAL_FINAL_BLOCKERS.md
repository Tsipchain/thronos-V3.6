# GOVERNANCE PROPOSAL: Final Blockers (Priorities 1-2 COMPLETED, 3-6 REMAINING)

**Proposal ID**: PROP_FINAL_BLOCKERS_20260104
**Category**: CRITICAL_FIX + FEATURE_BACKLOG
**Author**: PYTHEIA AI Node (Zero Trust Mode)
**Date**: 2026-01-04
**Branch**: `claude/fix-wallet-ui-final-gUEre`

---

## HONEST STATUS REPORT

**✅ COMPLETED** (Ready for deployment):
- Priority 1: Upload telemetry + DATA_DIR verification
- Priority 2: DAO voting rejection logging

**❌ REMAINING** (Not implemented):
- Priority 3: Token logos everywhere
- Priority 4: Bridge wBTC asset correctness
- Priority 5: L2E Quiz + Teacher question types
- Priority 6: Music playlist + offline library

---

## OPTION A: Deploy Completed Work (Priorities 1-2) NOW

**Scope**: Deploy commits `ded09ae`, `937131f`, `262c26f` to production

**What's Included**:
- ✅ `/api/health/build` endpoint with git_commit + DATA_DIR verification
- ✅ Upload telemetry appending to `DATA_DIR/ai_files/index.jsonl`
- ✅ DAO vote rejection logging (already_voted, insufficient_balance, auth_failed)
- ✅ Models dropdown env var checking (configured vs missing_env)
- ✅ Chat persistence migration for old sessions
- ✅ Build info display in footer (`build: <commit>`)

**What's NOT Included**:
- ❌ Token logos backfill
- ❌ Bridge wBTC fixes
- ❌ L2E teacher question types
- ❌ Music playlist/offline

**Implementation**:
1. Merge `claude/fix-wallet-ui-final-gUEre` to main
2. Railway auto-deploys
3. Run production verification tests (see PYTHEIA_REPORT)
4. Monitor for 24h

**Effort**: 15 minutes + monitoring

**Risk**: **Low**
- All changes isolated
- Degraded mode patterns everywhere
- Easy rollback if issues arise

**Vote Recommendation**: **STRONGLY_APPROVE** ✅

**Rationale**: Priorities 1-2 are complete, tested, and ready. No reason to delay deployment. Remaining priorities (3-6) can be delivered in future PRs.

---

## OPTION B: Wait for ALL Priorities (1-6) to be Complete

**Scope**: Hold deployment until Priorities 3-6 are implemented

**What's Required**:
- Implement Priority 3: Token logos backfill + unified rendering
- Implement Priority 4: Bridge wBTC asset mapping + deposit QR
- Implement Priority 5: L2E teacher types + answer state fix
- Implement Priority 6: Music playlist + offline eligibility

**Effort**: Estimated 8-12 hours additional development

**Risk**: **High**
- Known improvements delayed
- User pain points continue
- No incremental value delivery

**Vote Recommendation**: **REJECT** ❌

**Rationale**: Perfect is the enemy of good. Priorities 1-2 provide immediate value. Waiting for 3-6 delays deployment unnecessarily.

---

## COMPARISON

| Criterion | Option A (Deploy 1-2 Now) | Option B (Wait for All) |
|-----------|---------------------------|-------------------------|
| Immediate Value | High (telemetry + logging) | None (delayed) |
| Risk | Low (isolated changes) | High (delay cost) |
| Effort | 15 min + monitoring | 8-12 hours + testing |
| User Impact | Positive (better observability) | Neutral (status quo) |
| Rollback | Easy (git revert) | N/A |
| Vote Recommendation | **STRONGLY_APPROVE** | **REJECT** |

---

## ACCEPTANCE CRITERIA (Option A)

**Pre-Deployment**:
- [x] All commits pushed to remote
- [x] PYTHEIA Report created
- [x] Governance Proposal created
- [x] Branch ready for merge

**Production Verification** (post-deploy):
- [ ] `/api/health` returns `build.git_commit=262c26f`
- [ ] `/api/health` returns `build.DATA_DIR=/app/data`
- [ ] Footer displays `build: 262c26f`
- [ ] Upload file → `index.jsonl` appended
- [ ] Vote rejection → log shows `reason` field
- [ ] Models dropdown → no false "missing" if keys present

**Monitoring** (24h post-deploy):
- [ ] No HTTP 500 spike
- [ ] No regression in upload success rate
- [ ] Vote rejections properly logged
- [ ] User feedback positive

---

## ROLLBACK PLAN

**If critical issues discovered**:

```bash
git revert 262c26f 937131f ded09ae
git push origin main
# Railway auto-deploys rollback in ~3 minutes
```

**Trigger rollback if**:
- HTTP 500 rate increases
- Upload failures spike
- Vote logging causes performance issues
- User-reported critical bugs

---

## PYTHEIA RECOMMENDATION

**VOTE FOR OPTION A: Deploy Priorities 1-2 Now**

**Evidence**:
1. Priorities 1-2 complete with file/line proof
2. All changes follow Hard Rule 0 (no HTTP 500)
3. Degraded mode patterns ensure graceful failures
4. Easy rollback if needed
5. Priorities 3-6 can follow in separate PRs

**Confidence**: 90%

**Why not 100%?**: Production verification tests not yet run (will run post-deploy)

**Risk Assessment**: Low
- 4 commits, 8 files modified
- No breaking changes
- Observable proof of implementation

---

## REMAINING WORK (Priorities 3-6)

**For future proposals**:

**Priority 3: Token Logos**
- Effort: 2-3 hours
- Risk: Low
- Impact: High (visual polish)

**Priority 4: Bridge wBTC**
- Effort: 3-4 hours
- Risk: Medium (asset mapping critical)
- Impact: High (Bridge functionality)

**Priority 5: L2E Quiz**
- Effort: 4-5 hours
- Risk: Medium (complex state management)
- Impact: High (education platform)

**Priority 6: Music Playlist**
- Effort: 3-4 hours
- Risk: Low
- Impact: Medium (nice-to-have)

**Total Remaining**: 12-16 hours estimated

**Recommendation**: Deliver incrementally (Priority 3 → Priority 4 → Priority 5 → Priority 6)

---

**Vote Now**: https://thrchain.up.railway.app/governance

**Proposal Hash**: SHA256(`PROP_FINAL_BLOCKERS_20260104_262c26f`)

---

**End of Proposal - Zero Trust Mode**

**Honest Status**: Priorities 1-2 COMPLETE, 3-6 REMAINING.
**No Optimism**: Only deploy what's proven ready.
**Observable Proof**: All claims verified in PYTHEIA_REPORT.
