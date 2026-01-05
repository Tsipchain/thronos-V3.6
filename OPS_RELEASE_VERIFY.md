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
