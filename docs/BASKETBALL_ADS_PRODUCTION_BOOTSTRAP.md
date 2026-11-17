# Basketball paid-ad production bootstrap

This procedure provisions publisher authentication and the two canonical
placements only. It does not change pricing, charging, weighting, balances,
rewards, pledges, staking, or consensus.

## Before starting

Use a private operator shell with history disabled. Resolve the production
project, environment, and service IDs before changing anything. Variable
changes trigger Railway redeploys by default, so use `--skip-deploys` while
staging this configuration and deploy only after the pull requests are merged
and the owner has approved release.

Generate three independent secrets of at least 32 random bytes. Keep them in
shell variables or a password manager; never paste them into tickets, pull
requests, comments, logs, or command arguments. The publisher secret must be
the same value during canonical bootstrap and in the Basketball service.

## Canonical publisher record

Run this on `node 1 Master`, against the persistent Earn database, after the
new code is present:

```bash
python scripts/bootstrap_basketball_publisher.py --earn-user-id <EARN_USER_ID>
```

Paste the publisher secret at the hidden prompt. The command is atomic and
idempotent. It prints the non-secret publisher ID and confirms that the
publisher, `basketball_sidebar`, and `basketball_header_interstitial` are
active. Re-running it updates the stored secret to the supplied value, keeps
one active row for each canonical placement, and deactivates duplicate rows.

## Railway variables to stage

On `node 1 Master`:

```bash
printf '%s' "$EARN_DELIVERY_SECRET" | railway variable set EARN_DELIVERY_SECRET --stdin --skip-deploys --project <THRONOS_PROJECT_ID> --environment <PRODUCTION_ENV_ID> --service <MASTER_SERVICE_ID>
```

On `basketball-market-api`:

```bash
railway variable set EARN_PUBLISHER_ID=<PUBLISHER_ID> --skip-deploys --project <BASKETBALL_PROJECT_ID> --environment <PRODUCTION_ENV_ID> --service <BASKETBALL_SERVICE_ID>
printf '%s' "$EARN_PUBLISHER_SECRET" | railway variable set EARN_PUBLISHER_SECRET --stdin --skip-deploys --project <BASKETBALL_PROJECT_ID> --environment <PRODUCTION_ENV_ID> --service <BASKETBALL_SERVICE_ID>
printf '%s' "$BASKETBALL_VIEWER_HASH_SECRET" | railway variable set BASKETBALL_VIEWER_HASH_SECRET --stdin --skip-deploys --project <BASKETBALL_PROJECT_ID> --environment <PRODUCTION_ENV_ID> --service <BASKETBALL_SERVICE_ID>
railway variable set EARN_AD_API_BASE=https://api.thronoschain.org --skip-deploys --project <BASKETBALL_PROJECT_ID> --environment <PRODUCTION_ENV_ID> --service <BASKETBALL_SERVICE_ID>
```

`EARN_AD_API_BASE` is optional because that canonical URL is the code default,
but setting it explicitly makes production intent auditable.

## Preflight after the approved release

Run inside `basketball-market-api` with its production environment:

```bash
python scripts/earn_ads_preflight.py
```

The command prints exactly seven yes/no lines and exits nonzero unless all are
`yes`. It never prints variable values, publisher credentials, proof tokens,
or request errors. Paid serving remains closed when any required local secret
is absent; local house-ad fallback remains available where configured.
