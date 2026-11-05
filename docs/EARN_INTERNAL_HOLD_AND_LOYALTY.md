# Seven-day Earn hold and Wallet Loyalty VIP

The internal Earn hold is seven full days (604800 seconds) from the first
verified provider receipt reaching Earn. A TimeWall task awaiting approval on
TimeWall has not yet started this hold. For example, a receipt arriving on
9 November becomes eligible on 16 November at the same instant of day.

Each receipt stores its own start, deadline, policy version and release time.
Provider retries, page refreshes and restarts do not reset the deadline. Existing
verified pending receipts acquire the policy using their original receipt time;
existing available balances are not relocked. Unverified generic credits do not
receive the hold or become eligible for automatic release.

The Master scheduler checks every minute. It releases only positive, finite,
non-reversed pending entries backed by their matching durable provider receipt,
with an intact seven-day deadline. The store rechecks NODE_ROLE, READ_ONLY and
SCHEDULER_ENABLED. Release updates the original row and records an audit event;
concurrent runs cannot release it twice. An elapsed browser countdown does not
perform a transition. While the worker is unavailable, the UI says that the
server release check is pending.

Provider clearance, provider ETA, provider payment to the treasury and internal
Earn release remain separate facts. Early provider clearance cannot bypass the
hold. Release does not fabricate provider clearance, a settlement reference,
reserve funding or a payout. Existing reserve and payout gates still apply.
Provider reversals remove the original reward before or after release.

Web Earn and Wallet PWA history details show the selected receipt's own deadline,
countdown, hold reason, provider metadata and recorded reversal reason where
received. Unknown provider reasons and dates remain unknown. Receipt details
are restricted to their owner. The live countdown uses the server clock and
monotonic elapsed time.

Wallet PWA has a direct **Leaderboard / VIP** action. It opens the shared Earn
leaderboard in the wallet and focuses its card. Existing signed Earn sessions
and verified wallet session restoration apply; otherwise Earn sign-in is
required. The ranking remains the same 30-day campaign across web and wallet.

Wallet Loyalty VIP is an Earn membership derived exclusively from the existing
verified Earn-to-THR-wallet link. A submitted address, query parameter or browser
claim cannot activate VIP. Linking still requires the existing expiring signed
challenge and applicable wallet approval. Only the caller's membership is
returned; ranking peers' wallet addresses and link state stay private. This
release adds membership recognition, not a score multiplier, APY, staking,
financial benefit or a TimeWall VIP subscription. Benefits and prizes must be
announced separately.

This release does not change TIMEWALL_POSTBACK_LIVE. Genuine callback verification
and live activation remain separate operational steps.
