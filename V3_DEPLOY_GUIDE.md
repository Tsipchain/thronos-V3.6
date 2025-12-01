# Thronos V3 Deployment Guide

This guide details how to deploy the Thronos Chain V3, including the new **Crypto Hunters** game integration and **AI Agent** features.

## 1. Prerequisites
- **Python 3.9+**
- **Node.js 14+** (for Crypto Hunters backend)
- **Railway Account** (or any VPS/PaaS provider)

## 2. Installation

### Local Deployment
1.  **Install Python Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Install Game Dependencies**:
    ```bash
    cd addons/crypto_hunters/backend
    npm install
    cd ../../..
    ```
3.  **Run All Services**:
    ```bash
    chmod +x start_all.sh
    ./start_all.sh
    ```
    - Thronos Chain: `http://localhost:3333`
    - Game Backend: `http://localhost:3000`

### Railway Deployment
1.  **Upload Code**: Push this repository to GitHub or use the Railway CLI.
2.  **Procfile**: Ensure the `Procfile` contains:
    ```
    web: ./start_all.sh
    ```
    *Note: You may need to ensure `node` is available in the Railway build image. If using a Python buildpack, you might need a custom Dockerfile or a multi-buildpack setup.*
3.  **Environment Variables**: Set the following in Railway:
    - `ADMIN_SECRET`: A strong secret for admin endpoints.
    - `DATA_DIR`: `/app/data` (Mount a volume here for persistence).
    - `PORT`: `3333` (Railway usually sets this, but `start_all.sh` expects it for the Python server).
    - `THRONOS_API_URL`: `http://localhost:3333` (for the AI Agent).

## 3. Verification

### Watcher Service
1.  Go to `/pledge`.
2.  Enter a **valid BTC address** that has sent >0.00001 BTC to `1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ`.
3.  The system should verify the transaction via `mempool.space` and issue a Thronos address.

### AI Agent
1.  The agent runs automatically in the background (if started via `start_all.sh` or manually).
2.  Check logs for `🤖 Agent deciding to act`.
3.  Verify it receives 10% of mining rewards in `ledger.json`.

### Crypto Hunters
1.  Access the admin panel at `/panel` (proxied or direct port access depending on setup).
2.  Verify it can connect to the Thronos API.

## 4. Troubleshooting
- **"Waiting for BTC payment"**: Ensure the BTC transaction has at least 1 confirmation.
- **Agent not acting**: Ensure the agent wallet has >10 THR.