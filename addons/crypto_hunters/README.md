# Crypto Hunters - Thronos Integration

This package contains the "Crypto Hunters" game, a Play-to-Earn RPG integrated with the Thronos Chain.

## Components
- **Backend (`/backend`)**: A Node.js Express server (`drx.js`) managing game logic, missions, items, and the bridge to Thronos.
- **Mobile Demo (`/mobile-demo`)**: A React Native application for the game client.
- **Docs (`/docs`)**: Game design documents and API references.

## Running the Game
To run the game backend alongside the Thronos Chain:

1.  **Prerequisites**: Ensure `node` (v14+) and `npm` are installed.
2.  **Start All**: Use the provided script in the root directory:
    ```bash
    ./start_all.sh
    ```
    This will start:
    - Thronos Chain Server on port `3333` (default)
    - Crypto Hunters Backend on port `3000`

## API Endpoints
- **Game API**: `http://localhost:3000/api/...`
- **Admin Panel**: `http://localhost:3000/panel`

## Bridge Configuration
The bridge allows transferring assets between the game (DRX currency) and Thronos Chain (THR).
- **DRX -> THR**: Players lock DRX in-game to mint wrapped tokens on Thronos.
- **THR -> DRX**: Players burn wrapped tokens on Thronos to unlock DRX in-game.

See `docs/bridge.md` for full protocol details.