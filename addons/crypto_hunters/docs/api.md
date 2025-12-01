# API Reference

This document describes the REST API exposed by the demo backend server
(`drx.js`).  All endpoints respond with JSON.  Where appropriate, the HTTP
status code indicates success (`200`) or error (`4xx`).

## Missions

- `GET /api/missions` — Returns an array of all available missions.
- `POST /api/missions/complete` — Completes a mission and awards game DRX.
  - Request body: `{ "wallet": "rExample", "missionId": "E1" }`.
  - Response: `{ "message": "Rewarded 100 Game DRX", "balance": 100 }`.

## Items

- `GET /api/items` — Lists all shop items.
- `POST /api/items/buy/:itemId` — Purchases an item.
  - Path parameter `itemId` must match an ID from the item list.
  - Request body: `{ "wallet": "rExample" }`.
  - Response: `{ "message": "purchased", "balance": 50, "inventory": ["I_SEC_BOOST"] }`.

## Wallet Status

- `GET /api/status/:wallet` — Returns the current game DRX balance, inventory and
  outstanding withdraw requests for a wallet.
  - Example: `{ "wallet": "rExample", "balance": 350, "inventory": ["I_HASH_TOOL"] }`.

## Withdraw Requests

- `POST /api/withdraw/:wallet` — Creates a withdraw request for the entire
  game DRX balance.  The balance is reset to zero and a new request object is
  stored with status `pending`.
- `GET /api/withdraw/requests` — (Admin only) List withdraw requests.
  - Optional query parameter `status=pending|approved|sent` filters by status.
- `POST /api/withdraw/approve/:id` — (Admin only) Approves a request and marks
  its status as `approved`.
- `POST /api/withdraw/mark-sent/:id` — (Admin only) Marks an approved request as
  sent and records a `sentAt` timestamp.

## Admin Authentication

Admin endpoints require the header `x-admin-key` with the secret admin key.
Define this key in the `ADMIN_KEY` property of `config.json` or via an
environment variable when running the server.

## Bridge Endpoints (Demo)

These endpoints handle requests to move game DRX between the XRPL and the Thronos Chain.  Η υλοποίηση στο demo δεν στέλνει πραγματικά tokens αλλά δημιουργεί εγγραφές που ο διαχειριστής μπορεί να εγκρίνει και να ολοκληρώσει μέσω του admin panel.  Η πλήρης ροή περιγράφεται στο `docs/bridge.md`.

* `POST /api/bridge/drx-to-thr` — Σώζει μια αίτηση μεταφοράς game DRX από το XRPL προς Thronos.
  * Request body: `{ "wallet": "rExample", "amount": 200, "thrAddress": "THR123..." }`
  * Αφαιρεί `amount` από το υπόλοιπο του παίκτη και δημιουργεί ένα νέο bridge request με status `pending`.
  * Response: `{ "request": { id, wallet, amount, thrAddress, type:"drx-to-thr", status:"pending" } }`

* `POST /api/bridge/thr-to-drx` — Σώζει μια αίτηση μεταφοράς wrapped DRX (στο Thronos) προς XRPL.
  * Request body: `{ "thrAddress": "THR123...", "amount": 100, "wallet": "rExample" }`
  * Δημιουργεί ένα νέο bridge request που θα πιστώσει game DRX στον παίκτη όταν ολοκληρωθεί.
  * Response: `{ "request": { id, wallet, amount, thrAddress, type:"thr-to-drx", status:"pending" } }`

* `GET /api/bridge/requests` — (Admin only) Επιστρέφει όλες τις bridge requests.  Προαιρετικό query `status=pending|approved|completed` φιλτράρει τα αποτελέσματα.

* `POST /api/bridge/approve/:id` — (Admin only) Θέτει το status μιας bridge request σε `approved` ώστε να ξεκινήσει η διαδικασία μεταφοράς.

* `POST /api/bridge/complete/:id` — (Admin only) Ολοκληρώνει τη διαδικασία.  Για requests `drx-to-thr` δεν γίνεται επιπλέον ενέργεια στο demo· για `thr-to-drx` προστίθεται το αντίστοιχο ποσό game DRX στο υπόλοιπο του παίκτη.