# External ASIC Pool Configuration — Thronos Network

## Supported hardware

Any SHA-256 ASIC miner with a web-based pool configuration UI:
- Bitmain Antminer (S9, S17, S19, S19 Pro, S21 series)
- MicroBT Whatsminer (M20, M30, M50 series)
- Canaan Avalon (A10, A11, A13 series)
- Any other SHA-256 miner with standard stratum support

## Pool settings

Enter these in your miner's web UI under **Pool Configuration**:

```
Pool URL  : stratum+tcp://api.thronoschain.org:3334
Worker    : YOUR_THR_ADDRESS.worker1
Password  : x
```

### Notes

- Replace `YOUR_THR_ADDRESS` with your actual THR wallet address (starts with `THR`)
- Worker suffix (`.worker1`) is optional but helps identify individual units
- Password is always `x` (required field, not used for auth)
- Port `3334` is the default stratum port. Check `https://api.thronoschain.org/api/miner-kit` for the current value.

## Model-specific examples

See the example files in this folder:
- `antminer_s19_example.txt` — Antminer S19 / S19 Pro
- `whatsminer_example.txt` — MicroBT Whatsminer M30 / M50
- `avalon_example.txt` — Canaan Avalon A12 / A13

## Failover pool

Configure a second pool pointing to a CPU fallback if available:
```
Pool 2 URL    : stratum+tcp://api.thronoschain.org:3334
Pool 2 Worker : YOUR_THR_ADDRESS.worker2
Pool 2 Pass   : x
```
