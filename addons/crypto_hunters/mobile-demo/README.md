# Mobile Demo

This directory contains a simple Expo/React Native application that connects to
the Crypto Hunters backend.  The app allows a player to:

- Set their XRPL wallet (blind address).
- View the game storyline (Greek edition).
- Complete missions and earn game DRX.
- View their balance and inventory, and request withdrawals.
- Purchase items from the shop.

## Running the demo

Install dependencies and start the Expo server:

```bash
cd mobile-demo
npm install
npx expo start
```

Use an emulator or the Expo Go mobile app to scan the QR code.  The app
assumes the backend is running on `http://localhost:3000`.  If you run the
server on a different machine or port, edit the `API` constant near the top
of `App.js`.