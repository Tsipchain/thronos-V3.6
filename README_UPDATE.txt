THRONOS CHAIN - UPDATE PACKAGE (v2.1)
=====================================

This package contains the latest updates for the Thronos Chain core, the AI Agent, and the Crypto Hunters game.

CONTENTS
--------
1. Core Server (server.py, phantom_*.py): Updated with new mining logic (Burn/AI/Miner split) and Recovery System.
2. Templates (templates/): Updated recovery.html and other UI improvements.
3. Addons (addons/):
   - ai_agent/: The autonomous agent with Backup & Phantom Whisper simulation.
   - crypto_hunters/: The full game package (Backend + Mobile Demo + Docs).

INSTALLATION INSTRUCTIONS (LIVE SERVER)
---------------------------------------
1. Stop your running server.
2. BACKUP your existing 'data' folder (where ledger.json, chain.json, etc. are stored).
3. Replace all files in your repository with the files in this package.
   - IMPORTANT: Do NOT overwrite your 'data' folder if it exists in the root.
   - If you are using Railway volume for /app/data, this update is safe as it does not contain a 'data' folder.
4. Install new dependencies if needed:
   - pip install -r requirements.txt (if you haven't already)
   - For Crypto Hunters: cd addons/crypto_hunters/backend && npm install
5. Restart the server:
   - python server.py
6. (Optional) Start the AI Agent:
   - python addons/ai_agent/agent_prototype.py
7. (Optional) Start the Crypto Hunters Game Server:
   - cd addons/crypto_hunters/backend && node drx.js

CHANGELOG
---------
- Added 'Secret/Passphrase' field to Recovery page.
- Implemented LSB Steganography for secure contracts.
- Updated Mining Rewards: 10% Burn, 10% AI Agent, 80% Miner.
- Added AI Agent with Blockchain Backup and Phantom Whisper simulation.
- Integrated Crypto Hunters game package under 'addons/'.