#!/bin/bash

# Start Thronos Chain Server (Background)
echo "🚀 Starting Thronos Chain Server..."
python3 server.py &
SERVER_PID=$!

# Start Crypto Hunters Backend (Background)
echo "🎮 Starting Crypto Hunters Backend..."
cd addons/crypto_hunters/backend
npm install --production
node drx.js &
GAME_PID=$!

# Wait for both
wait $SERVER_PID $GAME_PID