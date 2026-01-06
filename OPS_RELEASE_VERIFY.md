# Release Verification (OPS)

1. **Check health endpoint**
   - Open `/api/health` in the deployed environment.
   - Confirm `build_id` and `git_commit` are present.
2. **Verify footer build tag**
   - Load any page (e.g., `/`).
   - Ensure the footer shows the same `build_id` as `/api/health`.
3. **Spot-check AI + wallet UI**
   - Open the wallet history modal and confirm categories render.
   - Trigger an AI chat request with an enabled model; confirm no errors and credits only deduct on successful calls.
4. **AI provider status**
   - Call `/api/ai/provider_status` and verify providers report `configured`/`library_loaded` without exposing secrets.
5. **Chat session stability**
   - Reset a chat session (clear messages) and refresh; session should remain listed with messages intact.
   - Delete a chat session and confirm the UI switches to another session without "session not found" loops.
6. **Provider debugging**
   - Verify `/api/ai/provider_status` lists key sources checked and any last errors per provider.
   - `/api/ai/provider_status` and `/api/ai_models` agree on enabled providers when `THRONOS_AI_MODE` is `hybrid` or `all`.
7. **AI callability**
   - Chat request with a concrete model (e.g., `gpt-4.1-mini`) either succeeds or returns structured JSON with `call_attempted:false` and no charges.
8. **Session flows**
   - Deleting a session returns `{ok:true}`; the UI should move to another session without loading the deleted id.
   - Resetting/clearing messages must not prune the session; refreshing should still show it.
9. **Pools + history**
   - `/pools` shows non-zero TVL estimates using wallet USD logic.
   - Wallet history displays pool swaps/liquidity actions under the Swaps tab.
10. **Menu and language**
    - Wallet and language selectors remain visible and clickable at common desktop widths.
11. **TX ledger persistence**
    - Restart the server and confirm `/api/tx_feed` and viewer/wallet history still display past transfers/swaps/token transfers.
12. **Token + swap visibility**
    - Perform a token transfer and confirm it appears under Viewer → Transfers and Wallet → Tokens; ensure swaps still render in their tab.
13. **Modal click-through**
    - Open and close wallet/login modals and verify tabs/buttons remain clickable (no hidden overlays intercepting clicks).
14. **Music endpoints**
    - `/api/music/status` responds with connected metadata; Viewer → Music shows status/empty-state messaging instead of “Not Connected”.
15. **Session auth**
    - PATCH/DELETE chat session rename/delete endpoints return 200 (no 403) and changes persist after refresh.
16. **Token decimals + activity**
    - Viewer → Tokens shows correct decimals/supply per token (HPNNIS/JAM/MAR etc.) with “(default)” only when registry is missing decimals.
    - Token transfer amounts render with correct precision across Viewer Transfers and Wallet Tokens.
17. **Transfers detail completeness**
    - After a token transfer + swap, Viewer Transfers rows include asset/amount/from/to and swap pair details; Wallet history shows them under the correct tabs.
18. **L2E numbers**
    - Viewer → L2E cards/tables render numeric values (no NaN/undefined) even when courses have empty enrollments/completions.
19. **Offline/Thrai retrieval**
    - `/api/thrai/ask` responds using new prompts (no repetition of last answer) and can surface stored architect deliverables when queried.
