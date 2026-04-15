# L2E Pricing and Reward Model

## Pricing model
1. **Canonical rail**: THR.
2. **Course definition**: `price_thr` is source of truth.
3. **Fiat mirror**: `price_fiat_estimate_usd` = derived display from THR reference value.
4. **Stripe semantics**: mirrors THR price for access only.
5. **Teacher settlement**: THR only.

## Reward model
1. Course completion records participation/completion state.
2. Completion does **not** transfer reward automatically.
3. Reward issuance is performed at claim-time.
4. Claim gate requires:
   - completion_status = completed
   - reward_eligibility = eligible
   - reward_claimed_status = not_claimed
   - THR reward wallet present
   - policy allows claim

## Reward lifecycle
- `not_eligible`
- `eligible`
- `claimable`
- `claimed`
- `rejected`
- `completed_without_wallet`

## Policy modes
- `manual_claim`: active.
- `teacher_approval`: modeled, pending approval workflow endpoints/UI.
- `admin_approval`: modeled, pending approval workflow endpoints/UI.

## Safety guarantees
- No automatic reward payout on completion.
- No claim payout without THR wallet.
- No independent Stripe-denominated pricing decisions.
