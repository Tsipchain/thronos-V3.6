# Crypto Hunters Whitepaper (Draft)

## Overview

Crypto Hunters is a Web3 role‑playing game that blends educational
cyber‑security puzzles with an engaging narrative.  Players earn an off‑chain
token (Game DRX) by completing missions.  Game DRX can be redeemed 1:1 for
DRX, an issued token on the XRP Ledger.  The game emphasises decentralisation
and real‑world security concepts in a fictional setting.

## Architecture

* **Game Server (Node/Express):** Hosts missions, tracks balances and
  inventories, and handles withdraw queues.  It exposes a JSON REST API for
  mobile clients and an admin panel.
* **Admin Panel:** A browser interface used by game operators to approve and
  finalise withdraw requests.  Withdrawals are manual to mitigate fraud.
* **XRPL Bot:** A separate service that monitors approved requests and
  dispatches corresponding issued‑currency payments from the authorised game
  wallet on the XRPL.
* **Blind Address Model:** Players earn off‑chain Game DRX mapped to a
  pseudonymous wallet ID.  Only when the player requests withdrawal does the
  XRPL address become relevant.  This model reduces the chance of
  inadvertently exposing a player’s real wallet on‑chain.
* **Data Seeds:** Mission definitions and shop items are stored in JSON files
  and loaded at runtime.

* **Cross‑Chain Bridge (Demo):** A minimal bridge component records
  requests to move Game DRX between the XRP Ledger and the Thronos Chain.
  The bridge uses a `lock‑mint‑burn‑unlock` flow similar to cross‑chain
  bridges【989199418686017†L155-L203】.  Players can request to mint
  wrapped DRX on Thronos by locking their Game DRX in a bridge account,
  or burn wrapped tokens to reclaim Game DRX on the XRPL.  The demo
  records these requests and requires manual approval/ completion
  in the admin panel (see `docs/bridge.md`).

## Security & Anti‑Cheat

* **Rate limits:** Prevent abuse of mission endpoints.
* **Mission caps:** Limit the number of completions per time period.
* **Withdrawal reviews:** Introduce manual or automated approval steps.  The
  admin panel ensures that suspicious requests can be investigated before
  funds are dispatched.
* **Separation of concerns:** The payout wallet (Auth Wallet) is isolated from
  the game server and only accessed via the XRPL bot with restricted
  credentials.

## Tokenomics

* **Issuance:** Game DRX is minted by completing missions or through events.
* **Sinks:** Shop purchases (items and cosmetics), mission entry fees,
  governance fees, seasonal passes.
* **Exchange:** 1 Game DRX = 1 DRX.  When a player withdraws, the off‑chain
  Game DRX is destroyed and the equivalent on‑chain DRX is paid out from the
  Auth Wallet.  Conversely, players can deposit DRX to purchase Game DRX
  credits if future game mechanics require.

## Roadmap

1. **Alpha:** Core mission loop, offline Game DRX rewards, withdraw queue.
2. **Beta:** Deploy XRPL bot and integrate NFTs with passive buffs.  Introduce
   guilds and leaderboard seasons.
3. **v1.0:** Public release with governance voting, seasonal content and
   cross‑platform clients.
4. **Argotera:** Persistent MMO environment with shardable instances, global
   events and dynamic political factions.  Argotera will expand the narrative
   beyond Greece to a global decentralised civilisation.