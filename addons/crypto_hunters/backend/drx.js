const express = require('express');
const fs = require('fs');
const path = require('path');
const crypto = require('node:crypto');
const app = express();
const port = process.env.PORT || 3000;

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
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
} catch (_e) { /* defaults or env vars */ }

// ---------------------------------------------------------------------------
// Static data
// ---------------------------------------------------------------------------
const missions = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'missions.json'), 'utf8'));
const items = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'items.json'), 'utf8'));
const storyActs = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'story_acts.json'), 'utf8'));
const rewardPolicy = JSON.parse(fs.readFileSync(path.join(__dirname, 'data', 'reward_policy.json'), 'utf8'));

// Tier ordering for progression
const TIER_ORDER = ['Easy', 'Normal', 'Expert', 'Genius'];
const TIER_PREREQUISITES = {
  Easy: null,
  Normal: 'Easy',
  Expert: 'Normal',
  Genius: 'Expert'
};

// Group missions by tier
const missionsByTier = {};
for (const t of TIER_ORDER) {
  missionsByTier[t] = missions.filter((m) => m.tier === t);
}

// ---------------------------------------------------------------------------
// In-memory state (populated from save files on startup)
// ---------------------------------------------------------------------------
const players = {}; // wallet -> PlayerState

function defaultPlayerState(wallet) {
  const questStates = {};
  for (const m of missions) {
    questStates[m.id] = m.tier === 'Easy' ? 'available' : 'locked';
  }
  return {
    wallet,
    balance: 0,
    inventory: [],
    questStates,
    completedMissions: [],
    storyProgress: [1], // Act 1 unlocked by default
    stats: { totalDrxEarned: 0, missionsCompleted: 0, itemsBought: 0 },
    lastSaved: null
  };
}

function getPlayer(wallet) {
  if (!players[wallet]) {
    players[wallet] = defaultPlayerState(wallet);
  }
  return players[wallet];
}

// ---------------------------------------------------------------------------
// Save / Resume — JSON file persistence
// ---------------------------------------------------------------------------
const SAVES_DIR = path.join(__dirname, 'data', 'saves');
try { fs.mkdirSync(SAVES_DIR, { recursive: true }); } catch (_e) { /* exists */ }

function savePath(wallet) {
  const safe = wallet.replace(/[^a-zA-Z0-9_-]/g, '_');
  return path.join(SAVES_DIR, `${safe}.json`);
}

function persistPlayer(wallet) {
  const p = players[wallet];
  if (!p) return;
  p.lastSaved = new Date().toISOString();
  try {
    fs.writeFileSync(savePath(wallet), JSON.stringify(p, null, 2), 'utf8');
  } catch (_e) { /* non-fatal */ }
}

function loadAllSaves() {
  try {
    const files = fs.readdirSync(SAVES_DIR).filter((f) => f.endsWith('.json'));
    for (const file of files) {
      try {
        const data = JSON.parse(fs.readFileSync(path.join(SAVES_DIR, file), 'utf8'));
        if (data.wallet) {
          players[data.wallet] = data;
        }
      } catch (_e) { /* skip corrupt saves */ }
    }
  } catch (_e) { /* no saves dir */ }
}
loadAllSaves();

// ---------------------------------------------------------------------------
// Quest state helpers
// ---------------------------------------------------------------------------
function tierCompleted(player, tier) {
  const tierMissions = missionsByTier[tier] || [];
  return tierMissions.every((m) => player.completedMissions.includes(m.id));
}

function currentTier(player) {
  for (let i = TIER_ORDER.length - 1; i >= 0; i--) {
    if (tierCompleted(player, TIER_ORDER[i])) {
      const next = TIER_ORDER[i + 1];
      return next || TIER_ORDER[i]; // at highest completed or next
    }
  }
  return 'Easy';
}

function recalcUnlocks(player) {
  const events = [];

  for (const tier of TIER_ORDER) {
    const prereq = TIER_PREREQUISITES[tier];
    if (prereq && !tierCompleted(player, prereq)) continue;

    for (const m of missionsByTier[tier]) {
      if (player.questStates[m.id] === 'locked') {
        player.questStates[m.id] = 'available';
      }
    }

    // Check tier unlock event
    if (prereq && tierCompleted(player, prereq)) {
      const allWereLocked = missionsByTier[tier].some(
        (m) => player.questStates[m.id] === 'available' &&
               !player.completedMissions.includes(m.id)
      );
      if (allWereLocked) {
        events.push({ event: 'tier_unlock', tier, animation: 'tier_fanfare' });
      }
    }
  }

  // Story progression
  const storyMap = { Easy: 2, Normal: 3, Expert: 4 };
  for (const [tier, actId] of Object.entries(storyMap)) {
    if (tierCompleted(player, tier) && !player.storyProgress.includes(actId)) {
      player.storyProgress.push(actId);
      events.push({ event: 'story_unlock', actId, animation: 'chapter_reveal' });
    }
  }

  return events;
}

// ---------------------------------------------------------------------------
// Middleware
// ---------------------------------------------------------------------------
app.use(express.json());
app.use('/panel', express.static(path.join(__dirname, 'panel')));

function requireAdmin(req, res, next) {
  if ((req.headers['x-admin-key'] || '') !== CONFIG.ADMIN_KEY) {
    return res.status(401).json({ error: 'unauthorized', code: 'UNAUTHORIZED' });
  }
  next();
}

// CORS for local development
const cors = (() => { try { return require('cors'); } catch (_e) { return null; } })();
if (cors) app.use(cors());

// ---------------------------------------------------------------------------
// Mission endpoints
// ---------------------------------------------------------------------------

// GET /api/missions — list all missions with per-user quest states
app.get('/api/missions', (req, res) => {
  const wallet = req.query.wallet;
  if (!wallet) {
    return res.json(missions);
  }
  const player = getPlayer(wallet);
  const enriched = missions.map((m) => ({
    ...m,
    questState: player.questStates[m.id] || 'locked'
  }));
  res.json(enriched);
});

// POST /api/missions/start — move available → in_progress
app.post('/api/missions/start', (req, res) => {
  const { wallet, missionId } = req.body || {};
  if (!wallet || !missionId) {
    return res.status(400).json({ error: 'wallet and missionId required', code: 'MISSING_FIELDS' });
  }
  const m = missions.find((x) => x.id === missionId);
  if (!m) {
    return res.status(404).json({ error: 'mission not found', code: 'MISSION_NOT_FOUND' });
  }
  const player = getPlayer(wallet);
  const state = player.questStates[missionId];

  if (state === 'locked') {
    return res.status(400).json({ error: 'mission is locked — complete prerequisite tier first', code: 'MISSION_LOCKED' });
  }
  if (state === 'in_progress') {
    return res.json({ message: 'already in progress', missionId, questState: 'in_progress' });
  }
  if (state === 'completed') {
    return res.status(400).json({ error: 'mission already completed', code: 'ALREADY_COMPLETED' });
  }

  player.questStates[missionId] = 'in_progress';
  persistPlayer(wallet);
  res.json({
    message: `Mission ${missionId} started`,
    missionId,
    questState: 'in_progress',
    event: 'mission_start',
    animation: 'quest_activate'
  });
});

// POST /api/missions/complete — requires in_progress state
app.post('/api/missions/complete', (req, res) => {
  const { wallet, missionId } = req.body || {};
  if (!wallet || !missionId) {
    return res.status(400).json({ error: 'wallet and missionId required', code: 'MISSING_FIELDS' });
  }
  const m = missions.find((x) => x.id === missionId);
  if (!m) {
    return res.status(404).json({ error: 'mission not found', code: 'MISSION_NOT_FOUND' });
  }
  const player = getPlayer(wallet);
  const state = player.questStates[missionId];

  if (state === 'completed') {
    return res.status(400).json({ error: 'mission already completed', code: 'ALREADY_COMPLETED' });
  }
  if (state === 'locked') {
    return res.status(400).json({ error: 'mission is locked', code: 'MISSION_LOCKED' });
  }
  if (state !== 'in_progress') {
    return res.status(400).json({ error: 'mission must be started first (POST /api/missions/start)', code: 'NOT_STARTED' });
  }

  // Award DRX (placeholder — no real payout)
  player.questStates[missionId] = 'completed';
  player.completedMissions.push(missionId);
  player.balance += m.reward_drx;
  player.stats.totalDrxEarned += m.reward_drx;
  player.stats.missionsCompleted += 1;

  // Recalculate unlocks
  const unlockEvents = recalcUnlocks(player);
  persistPlayer(wallet);

  res.json({
    message: `Rewarded ${m.reward_drx} Game DRX`,
    balance: player.balance,
    missionId,
    questState: 'completed',
    event: 'mission_complete',
    animation: 'reward_burst',
    drx_earned: m.reward_drx,
    unlocks: unlockEvents
  });
});

// ---------------------------------------------------------------------------
// Story endpoints
// ---------------------------------------------------------------------------
app.get('/api/story', (req, res) => {
  const wallet = req.query.wallet;
  const player = wallet ? getPlayer(wallet) : null;

  const acts = storyActs.map((act) => ({
    id: act.id,
    title: act.title,
    subtitle: act.subtitle,
    unlocked: player ? player.storyProgress.includes(act.id) : act.id === 1
  }));
  res.json(acts);
});

app.get('/api/story/:actId', (req, res) => {
  const actId = parseInt(req.params.actId, 10);
  const wallet = req.query.wallet;
  const act = storyActs.find((a) => a.id === actId);
  if (!act) {
    return res.status(404).json({ error: 'act not found', code: 'ACT_NOT_FOUND' });
  }

  if (wallet) {
    const player = getPlayer(wallet);
    if (!player.storyProgress.includes(actId)) {
      return res.status(403).json({
        error: 'act is locked — complete the prerequisite tier to unlock',
        code: 'ACT_LOCKED',
        prerequisite_tier: act.prerequisite_tier
      });
    }
  }

  res.json(act);
});

// ---------------------------------------------------------------------------
// Dashboard endpoint
// ---------------------------------------------------------------------------
app.get('/api/dashboard/:wallet', (req, res) => {
  const wallet = req.params.wallet;
  const player = getPlayer(wallet);

  const activeMissions = [];
  for (const [mid, state] of Object.entries(player.questStates)) {
    if (state === 'in_progress') {
      const m = missions.find((x) => x.id === mid);
      if (m) activeMissions.push(m);
    }
  }

  const unlockedActs = storyActs
    .filter((a) => player.storyProgress.includes(a.id))
    .map((a) => ({ id: a.id, title: a.title }));

  res.json({
    wallet,
    balance: player.balance,
    inventoryCount: player.inventory.length,
    inventory: player.inventory,
    missionsCompleted: player.stats.missionsCompleted,
    missionsTotal: missions.length,
    currentTier: currentTier(player),
    storyActsUnlocked: unlockedActs,
    stats: player.stats,
    activeQuests: activeMissions,
    rewardPolicy: {
      enabled: rewardPolicy.enabled,
      note: rewardPolicy.note
    },
    lastSaved: player.lastSaved
  });
});

// ---------------------------------------------------------------------------
// Item endpoints
// ---------------------------------------------------------------------------
app.get('/api/items', (_req, res) => {
  res.json(items);
});

app.post('/api/items/buy/:itemId', (req, res) => {
  const { wallet } = req.body || {};
  const { itemId } = req.params;
  if (!wallet) {
    return res.status(400).json({ error: 'wallet required', code: 'MISSING_FIELDS' });
  }
  const item = items.find((x) => x.id === itemId);
  if (!item) {
    return res.status(404).json({ error: 'item not found', code: 'ITEM_NOT_FOUND' });
  }
  const player = getPlayer(wallet);
  if (player.balance < item.price_drx) {
    return res.status(400).json({ error: 'insufficient balance', code: 'INSUFFICIENT_BALANCE' });
  }
  player.balance -= item.price_drx;
  player.inventory.push(item.id);
  player.stats.itemsBought += 1;
  persistPlayer(wallet);

  res.json({
    message: 'purchased',
    balance: player.balance,
    inventory: player.inventory,
    event: 'item_acquired',
    animation: 'item_glow',
    item: { id: item.id, name: item.name }
  });
});

// ---------------------------------------------------------------------------
// Wallet status endpoint (backward compatible)
// ---------------------------------------------------------------------------
app.get('/api/status/:wallet', (req, res) => {
  const wallet = req.params.wallet;
  const player = getPlayer(wallet);
  res.json({
    wallet,
    balance: player.balance,
    inventory: player.inventory,
    requests: withdrawRequests.filter((r) => r.wallet === wallet),
    questStates: player.questStates,
    completedMissions: player.completedMissions,
    storyProgress: player.storyProgress,
    stats: player.stats
  });
});

// ---------------------------------------------------------------------------
// Withdraw queue
// ---------------------------------------------------------------------------
let withdrawRequests = [];

app.post('/api/withdraw/:wallet', (req, res) => {
  const wallet = req.params.wallet;
  const player = getPlayer(wallet);
  if (player.balance <= 0) {
    return res.status(400).json({ error: 'no balance', code: 'NO_BALANCE' });
  }
  const obj = {
    id: (Date.now() + Math.random()).toString(36),
    wallet,
    amount: player.balance,
    status: 'pending',
    createdAt: new Date().toISOString()
  };
  withdrawRequests.push(obj);
  player.balance = 0;
  persistPlayer(wallet);
  res.json({ message: 'queued', request: obj });
});

// --- Admin withdraw endpoints ---
app.get('/api/withdraw/requests', requireAdmin, (req, res) => {
  const status = req.query.status;
  const list = status ? withdrawRequests.filter((r) => r.status === status) : withdrawRequests;
  res.json(list);
});

app.post('/api/withdraw/approve/:id', requireAdmin, (req, res) => {
  const r = withdrawRequests.find((x) => x.id === req.params.id);
  if (!r) return res.status(404).json({ error: 'not found', code: 'NOT_FOUND' });
  r.status = 'approved';
  res.json(r);
});

app.post('/api/withdraw/mark-sent/:id', requireAdmin, (req, res) => {
  const r = withdrawRequests.find((x) => x.id === req.params.id);
  if (!r) return res.status(404).json({ error: 'not found', code: 'NOT_FOUND' });
  r.status = 'sent';
  r.sentAt = new Date().toISOString();
  res.json(r);
});

// ---------------------------------------------------------------------------
// Bridge endpoints (demo — unchanged logic, added error codes)
// ---------------------------------------------------------------------------
let bridgeRequests = [];

app.post('/api/bridge/drx-to-thr', (req, res) => {
  const { wallet, amount, thrAddress } = req.body || {};
  const amt = Number(amount);
  if (!wallet || !thrAddress || !amt || amt <= 0) {
    return res.status(400).json({ error: 'wallet, thrAddress and positive amount required', code: 'MISSING_FIELDS' });
  }
  const player = getPlayer(wallet);
  if (player.balance < amt) {
    return res.status(400).json({ error: 'insufficient balance', code: 'INSUFFICIENT_BALANCE' });
  }
  player.balance -= amt;
  const obj = {
    id: (Date.now() + Math.random()).toString(36),
    wallet, thrAddress, amount: amt,
    type: 'drx-to-thr', status: 'pending',
    createdAt: new Date().toISOString()
  };
  bridgeRequests.push(obj);
  persistPlayer(wallet);
  res.json({ request: obj, balance: player.balance });
});

app.post('/api/bridge/thr-to-drx', (req, res) => {
  const { thrAddress, amount, wallet } = req.body || {};
  const amt = Number(amount);
  if (!thrAddress || !wallet || !amt || amt <= 0) {
    return res.status(400).json({ error: 'thrAddress, wallet and positive amount required', code: 'MISSING_FIELDS' });
  }
  const obj = {
    id: (Date.now() + Math.random()).toString(36),
    wallet, thrAddress, amount: amt,
    type: 'thr-to-drx', status: 'pending',
    createdAt: new Date().toISOString()
  };
  bridgeRequests.push(obj);
  res.json({ request: obj });
});

app.get('/api/bridge/requests', requireAdmin, (req, res) => {
  const status = req.query.status;
  const list = status ? bridgeRequests.filter((r) => r.status === status) : bridgeRequests;
  res.json(list);
});

app.post('/api/bridge/approve/:id', requireAdmin, (req, res) => {
  const r = bridgeRequests.find((x) => x.id === req.params.id);
  if (!r) return res.status(404).json({ error: 'not found', code: 'NOT_FOUND' });
  r.status = 'approved';
  r.approvedAt = new Date().toISOString();
  res.json(r);
});

app.post('/api/bridge/complete/:id', requireAdmin, (req, res) => {
  const r = bridgeRequests.find((x) => x.id === req.params.id);
  if (!r) return res.status(404).json({ error: 'not found', code: 'NOT_FOUND' });
  if (r.status !== 'approved') {
    return res.status(400).json({ error: 'request must be approved before completion', code: 'NOT_APPROVED' });
  }
  r.status = 'completed';
  r.completedAt = new Date().toISOString();
  if (r.type === 'thr-to-drx') {
    const player = getPlayer(r.wallet);
    player.balance += r.amount;
    persistPlayer(r.wallet);
  }
  res.json(r);
});

// ---------------------------------------------------------------------------
// Reward policy endpoint (read-only)
// ---------------------------------------------------------------------------
app.get('/api/reward-policy', (_req, res) => {
  res.json(rewardPolicy);
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------
app.use((_req, res) => {
  res.status(404).json({ error: 'endpoint not found', code: 'NOT_FOUND' });
});

app.use((err, _req, res, _next) => {
  console.error('Server error:', err);
  res.status(500).json({ error: 'internal server error', code: 'INTERNAL_ERROR' });
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
if (require.main === module) {
  app.listen(port, () => {
    console.log(`Crypto Hunters API @ http://localhost:${port}`);
    console.log(`Admin panel @ http://localhost:${port}/panel`);
    console.log(`Loaded ${missions.length} missions, ${items.length} items, ${storyActs.length} story acts`);
    console.log(`Restored ${Object.keys(players).length} player save(s)`);
  });
}

module.exports = { app, getPlayer, players, missions, items, storyActs, rewardPolicy, TIER_ORDER, missionsByTier };
