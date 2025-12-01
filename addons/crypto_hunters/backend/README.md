# Backend (v3)

This folder contains the Node/Express implementation of the Crypto Hunters demo
API.  It handles mission completion, item purchases, wallet balances and
withdraw queues.  An admin panel is provided for approving and marking
withdraw requests.  See the top‑level `README.md` for general usage.

## Running the server

From the `backend` directory:

```bash
npm install express
node drx.js
```

By default, the server runs on port 3000.  Missions and items are loaded from
JSON files in `data/`.  Balances and withdraw requests are stored in memory.

If you wish to customise the admin key, the XRPL network endpoint or the
payout wallet, create a `config.json` file based on `config.example.json` and
update the values accordingly.  You can also use environment variables to
override these values (`ADMIN_KEY`, `XRPL_NETWORK`, `AUTH_WALLET_SEED`,
`CURRENCY_CODE`, `ISSUER`).

## Admin panel

Navigate to `http://localhost:3000/panel` while the server is running.  Enter
your admin key and use the buttons to load **withdraw** or **bridge**
requests.  Withdraw requests represent players cashing out their game DRX,
while bridge requests are cross‑chain transfers between the XRPL and the
Thronos Chain.  You can approve or mark withdraws as sent, and you can
approve or complete bridge requests.  The panel is intentionally minimal and
intended for demonstration purposes only.

## XRPL bot

The `bot_stub.js` script provides a skeleton implementation for an XRPL
payout bot.  It polls the server for approved withdraw requests, constructs
issued‑currency payments and submits them to the XRPL.  After each payout,
the bot notifies the server to mark the request as sent.  To run it, install
the `xrpl` and `node-fetch` packages and ensure your `config.json` specifies
valid testnet credentials.

## Bridge demo

Starting from version 4 of the demo, the backend exposes basic bridge
endpoints for moving game DRX between the XRPL and the Thronos Chain.  These
endpoints do not perform real cross‑chain transfers; they simply record
requests that an administrator can approve and complete via the admin API.
See `docs/bridge.md` for an overview of the flow and `docs/api.md` for
details on each endpoint.  The admin panel now includes the ability to
load, approve and complete bridge requests.