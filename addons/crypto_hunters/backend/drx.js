const express = require('express');
const fs = require('fs');
const path = require('path');
const app = express();
const port = 3000;

// Load configuration.  You can override these values via a config.json file or
// environment variables.  The config defines the admin key used for
// authentication, the XRPL network endpoint, the seed of the payout wallet,
// and details of the issued currency (code and issuer address).
let CONFIG = {
  ADMIN_KEY: process.env.ADMIN_KEY || 'changeme',
  XRPL_NETWORK: process.env.XRPL_NETWORK || 'wss://s.altnet.rippletest.net:51233',
  AUTH_WALLET_SEED: process.env.AUTH_WALLET_SEED || 'sEXAMPLE_REPLACE_ME',
  CURRENCY_CODE: process.env.CURRENCY_CODE || 'DRX',
  ISSUER: process.env.ISSUER || 'rEXAMPLE_ISSUER'
};
try {
  const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));
  CONFIG = { ...CONFIG, ...cfg };
} catch (e) {
  // no custom config found; defaults or env vars will be used
}

app.use(express.json());
app.use('/panel', express.static(path.join(__dirname, 'panel')));

// Data stores (for demo purposes only — replace with a database for production)
let userBalances = {};     // wallet -> balance in game DRX
let inventories = {};      // wallet -> array of item IDs
let withdrawRequests = []; // array of { id, wallet, amount, status, createdAt, sentAt? }

// Load static seeds for missions and items
const missions = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'missions.json'), 'utf8'));
const items = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'items.json'), 'utf8'));

// Helper: ensure admin header is present
function requireAdmin(req, res, next) {
  if ((req.headers['x-admin-key'] || '') !== CONFIG.ADMIN_KEY) {
    return res.status(401).json({ error: 'unauthorized' });
  }
  next();
}

// --- Mission endpoints ---
app.get('/api/missions', (req, res) => {
  res.json(missions);
});

app.post('/api/missions/complete', (req, res) => {
  const { wallet, missionId } = req.body || {};
  if (!wallet || !missionId) {
    return res.status(400).json({ error: 'wallet and missionId required' });
  }
  const m = missions.find((x) => x.id === missionId);
  if (!m) {
    return res.status(404).json({ error: 'mission not found' });
  }
  userBalances[wallet] = (userBalances[wallet] || 0) + m.reward_drx;
  return res.json({ message: `Rewarded ${m.reward_drx} Game DRX`, balance: userBalances[wallet] });
});

// --- Item endpoints ---
app.get('/api/items', (req, res) => {
  res.json(items);
});

app.post('/api/items/buy/:itemId', (req, res) => {
  const { wallet } = req.body || {};
  const { itemId } = req.params;
  if (!wallet) {
    return res.status(400).json({ error: 'wallet required' });
  }
  const item = items.find((x) => x.id === itemId);
  if (!item) {
    return res.status(404).json({ error: 'item not found' });
  }
  const bal = userBalances[wallet] || 0;
  if (bal < item.price_drx) {
    return res.status(400).json({ error: 'insufficient balance' });
  }
  userBalances[wallet] = bal - item.price_drx;
  inventories[wallet] = (inventories[wallet] || []).concat(item.id);
  return res.json({ message: 'purchased', balance: userBalances[wallet], inventory: inventories[wallet] });
});

// --- Wallet status endpoint ---
app.get('/api/status/:wallet', (req, res) => {
  const wallet = req.params.wallet;
  res.json({
    wallet,
    balance: userBalances[wallet] || 0,
    inventory: inventories[wallet] || [],
    requests: withdrawRequests.filter((r) => r.wallet === wallet)
  });
});

// --- Withdraw queue ---
app.post('/api/withdraw/:wallet', (req, res) => {
  const wallet = req.params.wallet;
  const amount = userBalances[wallet] || 0;
  if (amount <= 0) {
    return res.status(400).json({ error: 'no balance' });
  }
  const obj = {
    id: (Date.now() + Math.random()).toString(36),
    wallet,
    amount,
    status: 'pending',
    createdAt: new Date().toISOString()
  };
  withdrawRequests.push(obj);
  userBalances[wallet] = 0;
  res.json({ message: 'queued', request: obj });
});

// --- Admin endpoints ---
app.get('/api/withdraw/requests', requireAdmin, (req, res) => {
  const status = req.query.status;
  const list = status ? withdrawRequests.filter((r) => r.status === status) : withdrawRequests;
  res.json(list);
});

app.post('/api/withdraw/approve/:id', requireAdmin, (req, res) => {
  const id = req.params.id;
  const r = withdrawRequests.find((x) => x.id === id);
  if (!r) {
    return res.status(404).json({ error: 'not found' });
  }
  r.status = 'approved';
  res.json(r);
});

app.post('/api/withdraw/mark-sent/:id', requireAdmin, (req, res) => {
  const id = req.params.id;
  const r = withdrawRequests.find((x) => x.id === id);
  if (!r) {
    return res.status(404).json({ error: 'not found' });
  }
  r.status = 'sent';
  r.sentAt = new Date().toISOString();
  res.json(r);
});

// -----------------------------------------------------------------------------
// Bridge endpoints (demo)
//
// These endpoints queue cross‑chain bridge operations.  They do not send
// real assets but record a request that an administrator can approve and
// complete.  See docs/bridge.md for the flow.

// In‑memory store for bridge requests
let bridgeRequests = [];

// POST /api/bridge/drx-to-thr
// Move game DRX from the player's balance into the bridge queue to mint
// wrapped DRX on Thronos.  Expects JSON body with: wallet, amount, thrAddress.
app.post('/api/bridge/drx-to-thr', (req, res) => {
  const { wallet, amount, thrAddress } = req.body || {};
  const amt = Number(amount);
  if (!wallet || !thrAddress || !amt || amt <= 0) {
    return res.status(400).json({ error: 'wallet, thrAddress and positive amount required' });
  }
  const bal = userBalances[wallet] || 0;
  if (bal < amt) {
    return res.status(400).json({ error: 'insufficient balance' });
  }
  userBalances[wallet] = bal - amt;
  const obj = {
    id: (Date.now() + Math.random()).toString(36),
    wallet,
    thrAddress,
    amount: amt,
    type: 'drx-to-thr',
    status: 'pending',
    createdAt: new Date().toISOString()
  };
  bridgeRequests.push(obj);
  res.json({ request: obj, balance: userBalances[wallet] });
});

// POST /api/bridge/thr-to-drx
// Queue a request to credit game DRX after burning wrapped tokens on Thronos.
// Expects JSON body with: thrAddress, amount, wallet.
app.post('/api/bridge/thr-to-drx', (req, res) => {
  const { thrAddress, amount, wallet } = req.body || {};
  const amt = Number(amount);
  if (!thrAddress || !wallet || !amt || amt <= 0) {
    return res.status(400).json({ error: 'thrAddress, wallet and positive amount required' });
  }
  const obj = {
    id: (Date.now() + Math.random()).toString(36),
    wallet,
    thrAddress,
    amount: amt,
    type: 'thr-to-drx',
    status: 'pending',
    createdAt: new Date().toISOString()
  };
  bridgeRequests.push(obj);
  res.json({ request: obj });
});

// GET /api/bridge/requests
// List bridge requests.  Admin only.  Optional query param status.
app.get('/api/bridge/requests', requireAdmin, (req, res) => {
  const status = req.query.status;
  const list = status ? bridgeRequests.filter((r) => r.status === status) : bridgeRequests;
  res.json(list);
});

// POST /api/bridge/approve/:id
// Approve a bridge request (admin).
app.post('/api/bridge/approve/:id', requireAdmin, (req, res) => {
  const id = req.params.id;
  const r = bridgeRequests.find((x) => x.id === id);
  if (!r) {
    return res.status(404).json({ error: 'not found' });
  }
  r.status = 'approved';
  r.approvedAt = new Date().toISOString();
  res.json(r);
});

// POST /api/bridge/complete/:id
// Complete a bridge request (admin).  For thr-to-drx, credit the balance.
app.post('/api/bridge/complete/:id', requireAdmin, (req, res) => {
  const id = req.params.id;
  const r = bridgeRequests.find((x) => x.id === id);
  if (!r) {
    return res.status(404).json({ error: 'not found' });
  }
  if (r.status !== 'approved') {
    return res.status(400).json({ error: 'request must be approved before completion' });
  }
  r.status = 'completed';
  r.completedAt = new Date().toISOString();
  if (r.type === 'thr-to-drx') {
    userBalances[r.wallet] = (userBalances[r.wallet] || 0) + r.amount;
  }
  res.json(r);
});

app.listen(port, () => {
  console.log(`DRX Game API @ http://localhost:${port}`);
});