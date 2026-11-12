# CPX postback IP protection

The CPX postback route now requires both the documented MD5 signature and a
source address in CPX's published list:

- `157.90.97.92`
- `188.40.3.73`
- `2a01:4f8:d0a:30ff::2`

The app configures Werkzeug `ProxyFix(x_for=1)`, matching the single Railway
ingress proxy, and the route checks only Flask's resulting `request.remote_addr`.
It ignores `X-Forwarded-For`, `X-Real-IP`, and `CF-Connecting-IP` supplied as
request headers. Railway HTTP logs for the production callback route showed 27
CPX requests from `157.90.97.92`, all with HTTP 200 (2026-11-05 to 2026-11-13).

After this code is deployed, verify one genuine CPX callback reaches HTTP 200
and creates exactly one receipt, a retry for the same `trans_id` does not
duplicate THC, `status=2` reverses the same ledger entry, and an unlisted IP
gets HTTP 403. Only then confirm both security statements in the CPX dashboard.
