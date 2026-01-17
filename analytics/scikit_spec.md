# Thronos AI Ledger – scikit-learn Spec

This document describes how to use `scikit-learn` on top of the AI Interaction Ledger.

## Input data

Use `data/ai_ledger.jsonl` produced by `ai_ledger.record_interaction`. Each row contains:

- `ts`
- `provider`
- `model`
- `prompt_hash`
- `output_hash`
- `session_id`
- `wallet`
- `credits_used`
- `score`
- `meta`

You can load it in Python:

```python
import json

rows = []
with open("data/ai_ledger.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        rows.append(json.loads(line))
```

## 1. Clustering sessions

- Aggregate by `session_id` and compute features:
  - total_calls
  - avg_score
  - total_credits
  - provider_mix (percentage of calls per provider)

- Use `sklearn.preprocessing.StandardScaler` and `sklearn.cluster.KMeans` to cluster sessions
  into behaviour groups (e.g. "architect", "quantum research", "casual").

## 2. Anomaly detection on outputs

- Maintain a rolling feature vector per interaction:
  - length of output
  - score
  - latency (if available in meta)
  - provider encoded as one-hot

- Use `sklearn.ensemble.IsolationForest` to flag anomalies (very long / short / low-score outputs).

## 3. Provider recommendation

- For each interaction, compute:
  - use_case (taken from `meta["use_case"]` if available, or from UI)
  - provider
  - score

- Train a simple model:
  - Encode `use_case` as one-hot.
  - Target = provider.
  - Use `sklearn.linear_model.LogisticRegression` or `RandomForestClassifier`.

- At inference time, given a use_case and maybe expected latency / cost,
  the model suggests the top-1 or top-3 providers for the next call.

## 4. Export back to Thronos

- Periodically export:
  - cluster labels per wallet/session
  - anomaly flags
  - provider recommendation weights

- Store them in `data/ai_analytics.json` and let the Quantum UI render:
  - "Your profile: Architect / Hunter / Artist"
  - Warnings when the model quality drops.
  - Suggestions like "For coding tasks, Sonnet currently has higher score for you".
