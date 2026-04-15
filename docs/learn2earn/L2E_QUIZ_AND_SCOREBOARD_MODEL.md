# L2E Quiz and Scoreboard Model (Extension)

This document extends the existing quiz foundation without replacing it.

## Reused foundation
- Existing course quiz endpoints and quiz-attempt persistence.
- Existing question types:
  - `multiple_choice`
  - `multi_select`
  - `short_answer`
  - `true_false`

## Extended model
- Multiple questions per course (existing behavior retained).
- Per-question score weight via `question.weight` (default `1.0`).
- Weighted total scoring:
  - `weighted_correct`
  - `weighted_total`
  - `quiz_score` (0-100)
- Pass threshold support:
  - `pass_threshold_score` (fallback to existing pass score)

## Result states
Quiz submit and status outputs now include:
- `completion_status`
- `quiz_score`
- `pass_fail_status`
- `certificate_eligibility`
- `reward_eligibility`

## Scoreboard compatibility
- Existing scoreboard foundations remain compatible.
- New state fields are additive and backward-friendly.
