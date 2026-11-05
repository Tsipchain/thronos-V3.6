# First Earn beta leaderboard cycle

- Campaign: `earn-beta-2026-11-05`.
- Start: 5 November 2026, 00:00 Europe/Athens (inclusive).
- End: 5 December 2026, 00:00 Europe/Athens (exclusive).
- Duration: exactly 30 days. Fixed boundaries survive reloads, restarts and deployments.
- After the deadline the cycle is ended and results remain under review; it does not restart automatically.

Web Earn and the Wallet PWA use the same authenticated API and shared display.
An Earn Account is the ranking identity whether or not it has a linked wallet.
The API does not return emails, account IDs, wallet addresses, provider IDs or
individual receipt references. Stable HMAC pseudonyms identify participants.

Only positive rewards backed by a matching CPX, BitcoTasks, PureSpectrum or
TimeWall receipt count. The receipt must belong to the same account and ledger
entry. Receipt time determines the cycle, including historical receipts already
received since the start of this launch day. Earlier pilot receipts are excluded.

The score is pending plus cleared THC, calculated with Decimal. Pending amounts
are provisional and are displayed separately from cleared amounts. Reversed
receipts are removed, including reversals arriving after the deadline. Generic
credits, browser activity, workouts and wallet balances cannot inflate a score.
Provider retries and later clearance do not duplicate it. Equal scores share a
rank, with stable pseudonym ordering within ties. The top 50 are shown; the
caller's own rank and totals are returned even outside the visible top.

The display refreshes every minute, on focus/visibility, or via Refresh. The
countdown uses the server timestamp and monotonic elapsed time instead of the
device's wall clock. API errors are shown as unavailable refreshes, not as an
invented zero-user ranking.

Ranking reads do not write rewards or audit events. Prize payment, staking,
wallet unlock, reward clearance, treasury transfers and cash-out are not enabled
by this release. Prizes for this cycle will be announced separately.

The all-provider tests also exposed an existing PureSpectrum INSERT with eight
placeholders for nine columns. The release fixes that INSERT with an explicit
column list; it does not enable PureSpectrum or any postback flag.
