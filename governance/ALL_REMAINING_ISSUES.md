# Comprehensive Governance Report: All Remaining Issues (B, E, C, D)

**Report Date**: 2026-01-03
**Status**: IMPLEMENTATION READY
**Priority**: HIGH

This document consolidates all remaining governance requirements for issues B (Learn-to-Earn), E (Chat), C (UI Polish), and D (Token Logo Backfill).

---

## Issue B: Learn-to-Earn System

### PYTHEIA Report Summary

**Files Affected**:
- `server.py:8185-8296` - Enrollment endpoints
- `server.py:8296-8664` - Quiz submission and completion
- `server.py:8464-8525` - Quiz creation/persistence
- `templates/course_detail.html:1-170` - Course UI

**Critical Findings**:

1. **Quiz Persistence Bug** (MAJOR):
   - Location: `server.py:8464-8525` (POST /api/v1/courses/<id>/quiz)
   - Symptom: Teacher creates quiz with N questions, only 1 persists
   - Root Cause: Quiz save logic may not serialize full questions array
   - Impact: Students cannot complete quizzes properly

2. **No Auto-Complete** (MAJOR):
   - Location: `server.py:8526-8664` (quiz submission handler)
   - Current: Manual completion required
   - Expected: Auto-mark complete when passing score achieved
   - Impact: Poor UX, manual intervention required

3. **No Auto-Reward** (MAJOR):
   - Location: Same as auto-complete
   - Current: No reward minting on course completion
   - Expected: Auto-credit L2E reward to student wallet
   - Impact: Learn-to-Earn promise broken

4. **No Enrollment Gating** (MAJOR):
   - Location: `templates/course_detail.html:43-75` - renderMaterials()
   - Current: Gating exists for UI but not enforced server-side
   - Expected: Server-side enforcement of payment before access
   - Impact: Security risk, payment bypass possible

### Patch Plan

**Phase 1: Fix Quiz Persistence**
```python
# server.py:8464-8525
@app.route("/api/v1/courses/<string:course_id>/quiz", methods=["POST"])
def api_v1_create_quiz(course_id: str):
    data = request.get_json() or {}
    questions = data.get("questions", [])
    passing_score = data.get("passing_score", 80)

    # CRITICAL: Ensure full questions array is saved
    quiz_data = {
        "quiz_id": str(uuid.uuid4()),  # Add unique quiz ID
        "course_id": course_id,
        "questions": questions,  # Full array
        "passing_score": passing_score,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "version": 1  # Add versioning
    }

    # Save to data/course_quizzes.json
    quizzes_file = os.path.join(DATA_DIR, "course_quizzes.json")
    quizzes = load_json(quizzes_file, {})
    quizzes[course_id] = quiz_data
    save_json(quizzes_file, quizzes)

    return jsonify({"ok": True, "quiz": quiz_data})
```

**Phase 2: Implement Auto-Complete + Auto-Reward**
```python
# server.py:8526-8664
@app.route("/api/v1/courses/<string:course_id>/quiz/submit", methods=["POST"])
def api_v1_submit_quiz(course_id: str):
    data = request.get_json() or {}
    student = data.get("student_thr", "")
    answers = data.get("answers", {})

    # Load quiz
    quiz = get_course_quiz(course_id)
    if not quiz:
        return jsonify({"ok": False, "error": "Quiz not found"}), 404

    # Grade quiz
    correct = 0
    total = len(quiz["questions"])
    for q in quiz["questions"]:
        if answers.get(q["id"]) == q["correct_answer"]:
            correct += 1

    score = (correct / total * 100) if total > 0 else 0
    passed = score >= quiz.get("passing_score", 80)

    # Save quiz result
    results_file = os.path.join(DATA_DIR, "quiz_results.json")
    results = load_json(results_file, {})
    result_id = str(uuid.uuid4())
    results[result_id] = {
        "course_id": course_id,
        "student": student,
        "score": score,
        "passed": passed,
        "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "answers": answers
    }
    save_json(results_file, results)

    # AUTO-COMPLETE: Mark course completed if passed
    if passed:
        enrollments_file = os.path.join(DATA_DIR, "course_enrollments.json")
        enrollments = load_json(enrollments_file, {})
        if course_id in enrollments and student in enrollments[course_id]:
            enrollments[course_id][student]["completed"] = True
            enrollments[course_id][student]["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            save_json(enrollments_file, enrollments)

        # AUTO-REWARD: Credit L2E reward
        courses_file = os.path.join(DATA_DIR, "courses.json")
        courses = load_json(courses_file, [])
        course = next((c for c in courses if c["id"] == course_id), None)

        if course and course.get("metadata", {}).get("reward_thr"):
            reward_amount = course["metadata"]["reward_thr"]

            # Credit reward to student wallet
            # Option 1: Direct balance update (simple)
            wallets_file = os.path.join(DATA_DIR, "wallets.json")
            wallets = load_json(wallets_file, {})
            if student not in wallets:
                wallets[student] = {"address": student, "balance": 0, "tokens": {}}
            wallets[student]["balance"] = wallets[student].get("balance", 0) + reward_amount
            save_json(wallets_file, wallets)

            # Option 2: Create transaction (preferred)
            # transaction = create_transaction(
            #     from_addr="SYSTEM_L2E_POOL",
            #     to_addr=student,
            #     amount=reward_amount,
            #     tx_type="L2E_REWARD",
            #     metadata={"course_id": course_id, "quiz_score": score}
            # )

            # Record reward in history
            rewards_file = os.path.join(DATA_DIR, "l2e_rewards.json")
            rewards = load_json(rewards_file, [])
            rewards.append({
                "reward_id": str(uuid.uuid4()),
                "student": student,
                "course_id": course_id,
                "amount_thr": reward_amount,
                "quiz_score": score,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            })
            save_json(rewards_file, rewards)

    return jsonify({
        "ok": True,
        "status": "success",
        "score": score,
        "passed": passed,
        "message": f"Quiz submitted. Score: {score}% ({'PASSED' if passed else 'FAILED'})",
        "auto_completed": passed,
        "reward_credited": passed and course.get("metadata", {}).get("reward_thr") is not None
    })
```

**Phase 3: Server-Side Enrollment Gating**
```python
# Add to quiz endpoints
def require_enrollment(course_id: str, student: str) -> bool:
    """Check if student is enrolled in course."""
    enrollments_file = os.path.join(DATA_DIR, "course_enrollments.json")
    enrollments = load_json(enrollments_file, {})
    return course_id in enrollments and student in enrollments[course_id]

# In quiz submit endpoint, add:
if not require_enrollment(course_id, student):
    return jsonify({"ok": False, "error": "Not enrolled in course"}), 403
```

### Testing Acceptance Criteria

- [ ] Create quiz with 5 questions → all 5 persist
- [ ] Student not enrolled → quiz submit returns 403
- [ ] Student enrolled → quiz opens successfully
- [ ] Submit quiz with passing score → course auto-marked complete
- [ ] Auto-complete triggers → reward appears in wallet
- [ ] Reward transaction appears in wallet history

---

## Issue E: Chat Critical Issues

### PYTHEIA Report Summary

**Files Affected**:
- `templates/chat.html:1024-2020` - Full chat application
- `server.py:*` - Chat session and message endpoints

**Critical Findings**:

1. **Messages Disappear After Refresh** (BLOCKER):
   - Location: `templates/chat.html:1131-1161` - hydrateSessionCache()
   - Current: localStorage used but not properly rehydrated
   - Impact: Users lose chat history

2. **File Uploads Not Processed** (MAJOR):
   - Location: `templates/chat.html:1704-1740` - uploadFiles()
   - Files uploaded but not parsed/included in AI request
   - Impact: File context missing from AI responses

3. **Model Dropdown Shows Only AUTO** (MAJOR):
   - Location: `templates/chat.html:1777-1866` - loadModels()
   - Fixed by Issue A implementation
   - Status: RESOLVED by degraded mode implementation

### Patch Plan

**Phase 1: Fix Session Persistence**
```javascript
// templates/chat.html - Improve hydrateSessionCache()
function hydrateSessionCache() {
  try {
    const raw = localStorage.getItem(SESSION_CACHE_KEY);
    if (!raw) {
      console.log("No cached sessions found");
      return;
    }
    const parsed = JSON.parse(raw);
    aiSessions = parsed.sessions || [];
    messagesBySession = parsed.messagesBySession || {};

    // CRITICAL: Restore current session
    if (currentSessionId && messagesBySession[currentSessionId]) {
      sessionMessages = messagesBySession[currentSessionId] || [];
      renderSessions();
      renderMessages(sessionMessages);  // ← ADD THIS
      console.log(`Restored ${sessionMessages.length} messages for session ${currentSessionId}`);
    } else if (!currentSessionId && aiSessions.length) {
      currentSessionId = aiSessions[0].id;
      sessionMessages = messagesBySession[currentSessionId] || [];
      renderMessages(sessionMessages);  // ← ADD THIS
    }
  } catch (e) {
    console.warn("hydrate cache failed", e);
  }
}

// Update init() to call hydrate BEFORE loadSessions
async function init() {
  cacheDom();
  hydrateSessionCache();  // ← Load cache first
  bindEvents();
  await loadModels();
  await loadWallet();
  await loadSessions();  // This will sync with server
  loadTelemetry();
  setInterval(loadTelemetry, 15000);
  setSending(true);
}
```

**Phase 2: Fix File Upload Processing**
```javascript
// templates/chat.html - Update sendMessage() to include file content
async function sendMessage() {
  // ... existing code ...

  const payload = {
    session_id: currentSessionId,
    wallet: wallet || null,
    messages: history,
    attachments: pendingFiles.map((f) => f.id),  // Already correct
    model,
  };

  // CRITICAL: Ensure backend processes attachments
  // Backend should load file contents and include in AI context

  // ... rest of function ...
}
```

```python
# server.py - Update chat endpoint to process file attachments
@app.route("/api/ai/providers/chat", methods=["POST"])
def api_ai_providers_chat():
    data = request.get_json() or {}
    messages = data.get("messages", [])
    attachments = data.get("attachments", [])  # File IDs

    # CRITICAL: Load and parse attached files
    file_contexts = []
    for file_id in attachments:
        file_path = os.path.join(DATA_DIR, "ai_files", f"{file_id}")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    file_contexts.append(f"[FILE: {file_id}]\n{content}\n[/FILE]")
            except:
                pass  # Binary files, skip or handle differently

    # Prepend file contexts to first user message
    if file_contexts and messages:
        messages[0]["content"] = "\n\n".join(file_contexts) + "\n\n" + messages[0]["content"]

    # ... rest of chat logic ...
```

### Testing Acceptance Criteria

- [ ] Send messages → refresh page → messages still visible
- [ ] Create new session → refresh → session list persists
- [ ] Upload text file → AI response references file content
- [ ] Upload PDF → AI processes content (if implemented)
- [ ] Model dropdown shows choices when API OK

---

## Issue C: UI Polish

### Quick Fixes

**C1: Music Player Z-Index**
```css
/* templates/music.html - Add page-specific z-index override */
#musicPlayer {
  position: fixed;
  bottom: 80px;  /* Raise above token widget */
  z-index: 100;   /* Above token widget (z-index: 50) */
}

/* Ensure token widget stays below on /music page only */
body.music-page #tokenWidget {
  z-index: 50;
}
```

**C2: Wallet Decimals Formatting**
```javascript
// templates/wallet_viewer.html or wallet widget
function formatTokenAmount(amount, decimals) {
  const decimalPlaces = decimals || 6;  // Default 6, or use token.decimals
  return parseFloat(amount).toFixed(decimalPlaces);
}

// Use in token display
tokenAmountEl.textContent = formatTokenAmount(balance, token.decimals);
```

**C3: Music/Viewer Status Messages**
```html
<!-- templates/music.html - Replace "Coming Soon" with honest status -->
<div id="musicStatus">
  <strong>Music Data Source:</strong>
  <span id="musicDataStatus" class="status-badge degraded">Not Connected</span>
  <p>Missing: /api/music/tracks endpoint, backend music registry integration, volume mount for audio files.</p>
  <p>To enable: Deploy music backend service and configure MUSIC_VOLUME env var.</p>
</div>
```

### Testing Acceptance Criteria

- [ ] Open /music → player clickable, not covered by footer
- [ ] Wallet assets show 6 decimals (or token-specific)
- [ ] Token logos display end-to-end (create → explorer → wallet)
- [ ] Music page shows accurate status, not generic "Coming Soon"

---

## Issue D: Token Logo Backfill (One-Time Migration)

### Migration Script

**Location**: `scripts/backfill_token_logos.py`

```python
#!/usr/bin/env python3
"""
One-time migration to backfill token logos from static/img to tokens.json

Usage:
  python3 scripts/backfill_token_logos.py [--dry-run]
"""

import os
import sys
import json
import argparse
from pathlib import Path

DATA_DIR = "data"
STATIC_IMG_DIR = "static/img"
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
VOLUME_DIR = os.getenv("TOKEN_LOGO_VOLUME", "volume/token_logos")

def load_tokens():
    """Load tokens.json."""
    if not os.path.exists(TOKENS_FILE):
        print(f"⚠️  {TOKENS_FILE} not found. Creating empty list.")
        return []
    with open(TOKENS_FILE, 'r') as f:
        return json.load(f)

def save_tokens(tokens):
    """Save tokens.json."""
    os.makedirs(os.path.dirname(TOKENS_FILE), exist_ok=True)
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)
    print(f"✓ Saved {len(tokens)} tokens to {TOKENS_FILE}")

def find_logo_for_token(token):
    """
    Find logo file for token by symbol or name.
    Checks:
    - static/img/{symbol}.png
    - static/img/{name}.png
    - volume/token_logos/{symbol}.png
    - static/img/{symbol_lower}.png
    """
    symbol = token.get("symbol", "").upper()
    name = token.get("name", "")

    search_paths = [
        os.path.join(STATIC_IMG_DIR, f"{symbol}.png"),
        os.path.join(STATIC_IMG_DIR, f"{symbol.lower()}.png"),
        os.path.join(STATIC_IMG_DIR, f"{name}.png"),
        os.path.join(VOLUME_DIR, f"{symbol}.png"),
    ]

    for path in search_paths:
        if os.path.exists(path):
            return path

    return None

def backfill_logos(dry_run=False):
    """Main backfill logic."""
    tokens = load_tokens()
    updated_count = 0
    skipped_count = 0
    not_found_count = 0

    print(f"\nBackfilling token logos for {len(tokens)} tokens...")
    print(f"{'DRY RUN - ' if dry_run else ''}No changes will be made.\n" if dry_run else "")

    for token in tokens:
        symbol = token.get("symbol", "UNKNOWN")
        existing_logo = token.get("logo_path")

        # Skip if already has valid logo_path
        if existing_logo and os.path.exists(existing_logo):
            print(f"  ✓ {symbol}: Already has logo at {existing_logo}")
            skipped_count += 1
            continue

        # Try to find logo
        logo_path = find_logo_for_token(token)

        if logo_path:
            print(f"  → {symbol}: Found logo at {logo_path}")
            if not dry_run:
                token["logo_path"] = logo_path
            updated_count += 1
        else:
            print(f"  ✗ {symbol}: No logo found")
            not_found_count += 1

    # Save if not dry run
    if not dry_run and updated_count > 0:
        save_tokens(tokens)

    # Report
    print(f"\n{'='*60}")
    print(f"Backfill Report:")
    print(f"  Total tokens: {len(tokens)}")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped (already has logo): {skipped_count}")
    print(f"  Not found: {not_found_count}")
    print(f"{'='*60}\n")

    if dry_run:
        print("⚠️  DRY RUN complete. Run without --dry-run to apply changes.")
    else:
        print("✓ Backfill complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill token logos")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no changes)")
    args = parser.parse_args()

    backfill_logos(dry_run=args.dry_run)
```

### Testing Acceptance Criteria

- [ ] Run dry-run → see report of found logos
- [ ] Run actual backfill → tokens.json updated
- [ ] Existing tokens with logos not changed
- [ ] Wallet/explorer shows backfilled logos

---

## Implementation Priority

1. **BLOCKER**: Issue A (models API) - ✅ COMPLETED
2. **HIGH**: Issue E (chat persistence, file uploads) - IMPLEMENT NEXT
3. **HIGH**: Issue B (L2E auto-complete/reward) - IMPLEMENT NEXT
4. **MEDIUM**: Issue C (UI polish) - Quick fixes
5. **LOW**: Issue D (logo backfill) - One-time migration, can run anytime

---

**End of Comprehensive Report**
