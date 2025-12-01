# Thronos V3.1 Update Guide

This guide lists the specific files you need to copy/paste to your existing repository to apply the V3.1 updates (Tokenomics, Dynamic Mining, AI Fixes) without re-uploading the entire project.

## 📂 Core Server Logic (Critical)
Replace these files to enable Dynamic Difficulty, Tokenomics, and AI Wallet Auto-Registration.

1.  **`server.py`**
    *   *Location*: Root folder (`thronos-V3/`)
    *   *Changes*: Added `/tokenomics`, `/mining_info`, Dynamic Difficulty Logic, AI Wallet Auto-Registration.

## 📄 Frontend Templates (UI)
Replace/Add these files to update the website look and navigation.

2.  **`templates/tokenomics.html`** (New File)
    *   *Location*: `thronos-V3/templates/`
    *   *Purpose*: Displays the Halving Schedule.

3.  **`templates/index.html`**
    *   *Location*: `thronos-V3/templates/`
    *   *Changes*: Added "Tokenomics" link to navigation.

4.  **`templates/wallet_viewer.html`**
    *   *Location*: `thronos-V3/templates/`
    *   *Changes*: Added "Tokenomics" link.

5.  **`templates/thronos_block_viewer.html`**
    *   *Location*: `thronos-V3/templates/`
    *   *Changes*: Added "Tokenomics" link.

6.  **`templates/pledge_form.html`**
    *   *Location*: `thronos-V3/templates/`
    *   *Changes*: Added "Tokenomics" link.

7.  **`templates/send.html`**
    *   *Location*: `thronos-V3/templates/`
    *   *Changes*: Added "Tokenomics" link.

8.  **`templates/recovery.html`**
    *   *Location*: `thronos-V3/templates/`
    *   *Changes*: Added "Tokenomics" link.

## ⛏️ Mining Kit
Update the miner script and the download package.

9.  **`miner_kit/pow_miner_cpu.py`**
    *   *Location*: `thronos-V3/miner_kit/`
    *   *Changes*: Added Dynamic Difficulty support.

10. **`static/miner_kit.zip`**
    *   *Location*: `thronos-V3/static/`
    *   *Changes*: Updated zip file containing the new miner.

## 🤖 AI Agent (Optional but Recommended)
11. **`addons/ai_agent/agent_prototype.py`**
    *   *Location*: `thronos-V3/addons/ai_agent/`
    *   *Changes*: (If you apply the AI updates)

---

## 🚀 Quick Deployment Steps
1.  **Stop** your running server.
2.  **Upload/Copy** the files listed above to their respective directories.
3.  **Restart** the server (`python server.py`).
4.  **Check** `data/ai_agent_credentials.json` (created automatically) to get the AI Agent's secret key.