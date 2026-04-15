# Learn2Earn Product Rules (Merge Baseline)

## 1) THR-first pricing
- THR is the canonical pricing unit for all courses.
- Teachers define course price in THR only.
- Teacher revenue is settled in THR only.
- Fiat (USD) display is derived from THR reference value and is display-only.
- Stripe is an access gateway mirroring THR price; it is not an independent pricing rail.

## 2) Reward issuance
- Rewards are controlled and claim-based.
- Lesson/course completion must not auto-send rewards.
- Reward can become claimable only when all are true:
  1. completion conditions satisfied
  2. learner is reward-eligible
  3. learner has THR wallet
  4. reward policy allows claim

## 3) Reward policies
- `manual_claim` → claim path available when eligibility conditions pass.
- `teacher_approval` → modeled, approval workflow pending.
- `admin_approval` → modeled, approval workflow pending.

## 4) Governance-safe wording
- Rewards must not be described as automatic earnings.
- UI/docs must avoid guaranteed payout language.
- Approved wording: educational participation + eligibility + claim flow.

## 5) Current implementation status
- THR-first pricing: implemented.
- Stripe mirror pricing/access: implemented.
- Controlled claim-time issuance: implemented.
- Teacher/admin approval workflow: modeled-but-pending.
