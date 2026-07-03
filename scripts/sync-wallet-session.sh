#!/usr/bin/env bash
# Sync the wallet_session.js copies.
#
# Source of truth: static/wallet_session.js
# Mirror served by Vercel/CDN static hosting: public/static/wallet_session.js
#
# Flask serves `static/wallet_session.js` at `/static/wallet_session.js` (loaded
# by templates/base.html and templates/chat.html). The Vercel edge site serves
# files under `public/` — `public/static/wallet_session.js` is the copy exposed
# to the marketing / static landing pages.
#
# Any change to the wallet session logic MUST be made in the canonical
# `static/wallet_session.js` and then this script re-run so the mirror
# stays byte-identical.
#
# CI hint: run this script and `git diff --exit-code public/static/wallet_session.js`
# to fail fast when the copies diverge.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/static/wallet_session.js"
DST="$REPO_ROOT/public/static/wallet_session.js"

if [[ ! -f "$SRC" ]]; then
  echo "error: canonical source not found: $SRC" >&2
  exit 1
fi

cp "$SRC" "$DST"
echo "Synced: $DST ← $SRC"
