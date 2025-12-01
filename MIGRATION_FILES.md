# Thronos V3.1 Migration Files

To update an existing Thronos V3 installation to V3.1 (Tokenomics, Dynamic Mining, AI Fixes, Game Beta, Whitepaper/Roadmap UI), copy the following files to your server, overwriting existing ones.

## 1. Core Server Logic
*   **`server.py`**: Updated with new routes (`/whitepaper`, `/roadmap`), Dynamic Difficulty, Halving logic, and AI Agent auto-registration.

## 2. Templates (Frontend)
*   **`templates/whitepaper.html`**: **(NEW)** Page displaying the Whitepaper.
*   **`templates/roadmap.html`**: **(NEW)** Page displaying the Roadmap.
*   **`templates/tokenomics.html`**: **(NEW)** Page displaying the Halving Schedule.
*   **`templates/index.html`**: Updated navigation & content.
*   **`templates/pledge_form.html`**: Updated navigation.
*   **`templates/wallet_viewer.html`**: Updated navigation.
*   **`templates/thronos_block_viewer.html`**: Updated navigation.
*   **`templates/send.html`**: Updated navigation.
*   **`templates/recovery.html`**: Updated navigation.

## 3. Mining Kit
*   **`miner_kit/pow_miner_cpu.py`**: Updated miner script.

## 4. Documentation & AI
*   **`addons/ai_agent/AI_AGENT_ANALYSIS.md`**: **(NEW)** Report on AI Agent.

## Instructions
1. Stop the server.
2. Upload/Overwrite these files.
3. Restart the server.