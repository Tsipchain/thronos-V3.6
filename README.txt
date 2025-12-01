================================================================================
   Thronos Chain V3.2 - Documentation
================================================================================

This package contains the complete source code for the Thronos Chain server,
mining tools, and IoT node integration.

--------------------------------------------------------------------------------
1. SERVER INSTALLATION
--------------------------------------------------------------------------------
Requirements:
- Python 3.8 or higher
- Dependencies: Flask, aiohttp, apscheduler, requests, pillow, cryptography

Installation:
1. Open a terminal/command prompt in this directory.
2. Install the required Python packages:
   pip install Flask aiohttp apscheduler requests pillow cryptography

Running the Server:
1. Execute the server script:
   python server.py

2. The server will start on port 3333 by default.
   Access the web interface at: http://localhost:3333

--------------------------------------------------------------------------------
2. MINER KIT USAGE (Dual Mining)
--------------------------------------------------------------------------------
The 'miner_kit' folder contains configuration files for mining Thronos (THR)
while dual-mining SHA256 coins (like Bitcoin) via a secondary pool.

Setup:
1. Download 'cgminer' (version 3.7.2 is recommended for broad compatibility,
   or a newer version supporting SHA256 ASICs).
2. Extract 'cgminer.exe' (and its DLLs) into the 'miner_kit' folder.

Configuration:
1. Open 'miner_kit/cgminer.conf' in a text editor.
2. Locate the line: "user": "THR_YOUR_WALLET_ADDRESS"
3. Replace "THR_YOUR_WALLET_ADDRESS" with your actual Thronos Wallet Address.
   (You can generate one via the /pledge page or use an existing one).
4. (Optional) Update the secondary pool URL/User if you want to mine something
   other than the default NiceHash pool.

Starting the Miner:
1. Double-click 'miner_kit/start_dual_mining.bat'.
2. A command window will open, launching the Thronos Stratum Proxy and then
   cgminer.
3. Monitor the window for accepted shares.

--------------------------------------------------------------------------------
3. IOT NODE SETUP
--------------------------------------------------------------------------------
Thronos supports IoT Vehicle Nodes that transmit telemetry data securely.

How to Register a Node:
1. Ensure the Thronos Server is running.
2. Navigate to: http://localhost:3333/iot
3. Locate the "Register New Node" section.
4. Enter your Wallet Address and a Secret Key (password).
5. Click "Download Node Kit (.zip)".

Running the Node:
1. Extract the downloaded 'iot_node_kit.zip' on your IoT device (e.g., Raspberry Pi, Laptop).
2. Ensure Python 3 is installed on the device.
3. Run the startup script:
   python start_iot.py

4. The node will begin transmitting telemetry data to the server, visible on the
   /iot dashboard.

--------------------------------------------------------------------------------
4. FEATURES OVERVIEW
--------------------------------------------------------------------------------
- Block Viewer (/viewer):
  View the latest blocks, transactions, and network statistics. Now includes
  Height, Pool Fees, and easy-copy buttons.

- Bitcoin Bridge (/bridge):
  Monitors the Bitcoin network for deposits to the designated bridge address.

- Recovery (/recovery):
  Recover wallet credentials using Steganography (uploading a key image).

- Pledge System (/pledge):
  Create new wallets by pledging BTC addresses. Generates a secure PDF contract.

- Tokenomics & Roadmap:
  Detailed information available at /tokenomics and /roadmap.

================================================================================