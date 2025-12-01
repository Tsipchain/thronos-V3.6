// XRPL payout bot (stub)
//
// This script illustrates how to automate the distribution of DRX on the XRPL
// based on approved withdraw requests.  For a real deployment you should add
// proper error handling, logging and secret management.  To run this bot you
// need to install the packages `xrpl` and `node-fetch`:
//   npm install xrpl node-fetch
//
const xrpl = require('xrpl');
const fetch = (...args) => import('node-fetch').then(({ default: fetch }) => fetch(...args));
const fs = require('fs');

// Load configuration.  This script expects the same config file used by the
// server.  For test environments, use the Ripple Testnet via the provided
// wss endpoint.
const CONFIG = JSON.parse(fs.readFileSync('./config.json', 'utf8'));
const API_BASE = process.env.API_BASE || 'http://localhost:3000';

async function main() {
  const client = new xrpl.Client(CONFIG.XRPL_NETWORK);
  await client.connect();
  const wallet = xrpl.Wallet.fromSeed(CONFIG.AUTH_WALLET_SEED);

  // Load all approved withdraw requests
  const headers = { 'x-admin-key': CONFIG.ADMIN_KEY };
  const res = await fetch(`${API_BASE}/api/withdraw/requests?status=approved`, { headers });
  const requests = await res.json();

  for (const req of requests) {
    try {
      // Construct an issued‑currency payment on the XRPL
      const tx = {
        TransactionType: 'Payment',
        Account: wallet.address,
        Destination: req.wallet,
        Amount: {
          currency: CONFIG.CURRENCY_CODE,
          issuer: CONFIG.ISSUER,
          value: String(req.amount)
        }
      };
      const prepared = await client.autofill(tx);
      const signed = wallet.sign(prepared);
      const result = await client.submitAndWait(signed.tx_blob);
      console.log(`Sent ${req.amount} ${CONFIG.CURRENCY_CODE} to ${req.wallet}:`, result.result.hash);

      // Notify the server that the payment has been sent
      await fetch(`${API_BASE}/api/withdraw/mark-sent/${req.id}`, {
        method: 'POST',
        headers
      });
    } catch (e) {
      console.error('Payout failed for request', req.id, e);
    }
  }
  client.disconnect();
}

main().catch((err) => {
  console.error('XRPL bot error:', err);
});