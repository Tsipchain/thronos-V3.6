## GPU Mining (Dev/Test)

SHA256 GPU mining is typically non-competitive in production, but the HTTP
contract can be used for testing or educational purposes.

Use the same endpoints as CPU mining:

- `GET /api/miner/work`
- `POST /api/miner/submit`

If you build a GPU miner, reuse the CPU contract fields (`nonce`, `pow_hash`,
`address`, optional `job_id`) and handle `409 stale_block` by refreshing work.
