# CPX postback IP protection

The CPX postback route now requires both the documented MD5 signature and a
source address in CPX's published list:

- `157.90.97.92`
- `188.40.3.73`
- `2a01:4f8:d0a:30ff::2`

Railway's edge records the direct callback source in `X-Real-IP`. The
application uses that value for this callback because the existing
`ProxyFix(x_for=1)` correctly exposes the offer participant's forwarded address
as `request.remote_addr`, not CPX's address. The MD5 signature, unique
`trans_id` handling, and reversal support remain mandatory.

Railway HTTP logs showed a real callback on 2026-11-12 whose edge source was
`157.90.97.92` while the forwarded participant address was different; this is
the reason the Railway source header is used.

After this code is deployed, verify one genuine CPX callback reaches HTTP 200
and creates exactly one receipt, a retry for the same `trans_id` does not
duplicate THC, `status=2` reverses the same ledger entry, and an unlisted IP
gets HTTP 403. Only then confirm both security statements in the CPX dashboard.
