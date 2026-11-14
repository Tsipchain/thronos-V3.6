const http = require('http');
const assert = require('assert');
const path = require('path');
const fs = require('fs');

// Clear any persisted saves before importing
const SAVES_DIR = path.join(__dirname, '..', 'data', 'saves');
try {
  const files = fs.readdirSync(SAVES_DIR).filter(f => f.endsWith('.json'));
  for (const f of files) fs.unlinkSync(path.join(SAVES_DIR, f));
} catch (_e) { /* ok */ }

const { app, missions, items, storyActs, rewardPolicy, TIER_ORDER, players, sessions } = require('../drx.js');

let server;
let BASE;

function req(method, urlPath, body, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlPath, BASE);
    const opts = { method, hostname: url.hostname, port: url.port, path: url.pathname + url.search, headers: {} };
    if (body) {
      const data = JSON.stringify(body);
      opts.headers['Content-Type'] = 'application/json';
      opts.headers['Content-Length'] = Buffer.byteLength(data);
    }
    if (token) opts.headers['Authorization'] = 'Bearer ' + token;
    const r = http.request(opts, (res) => {
      let chunks = '';
      res.on('data', (c) => chunks += c);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(chunks) });
        } catch (_e) {
          resolve({ status: res.statusCode, body: chunks });
        }
      });
    });
    r.on('error', reject);
    if (body) r.write(JSON.stringify(body));
    r.end();
  });
}

async function createAndAuth(callsign) {
  const r = await req('POST', '/api/player/create', { callsign, hunterClass: 'hacker', avatar: { bodyType: 'average' } });
  return r.body.sessionToken;
}

// Helpers
const W = 'rTestWallet12345';
const W2 = 'rTestWallet67890';

function clearPlayers() {
  for (const k of Object.keys(players)) delete players[k];
  for (const k of Object.keys(sessions)) delete sessions[k];
  try {
    const files = fs.readdirSync(SAVES_DIR).filter(f => f.endsWith('.json'));
    for (const f of files) fs.unlinkSync(path.join(SAVES_DIR, f));
  } catch (_e) { /* ok */ }
}

// ── Test runner ──────────────────────────────────────────────────────────────
const tests = [];
let passed = 0;
let failed = 0;

function test(name, fn) {
  tests.push({ name, fn });
}

async function run() {
  server = app.listen(0);
  const addr = server.address();
  BASE = `http://127.0.0.1:${addr.port}`;
  console.log(`Test server @ ${BASE}`);

  for (const t of tests) {
    clearPlayers();
    try {
      await t.fn();
      passed++;
      console.log(`  PASS  ${t.name}`);
    } catch (err) {
      failed++;
      console.log(`  FAIL  ${t.name}`);
      console.log(`        ${err.message}`);
    }
  }

  server.close();
  console.log(`\n${passed} passed, ${failed} failed, ${tests.length} total`);
  process.exit(failed > 0 ? 1 : 0);
}

// ── Static data tests ────────────────────────────────────────────────────────
test('static: missions loaded correctly', () => {
  assert.strictEqual(missions.length, 12);
  assert.deepStrictEqual(TIER_ORDER, ['Easy', 'Normal', 'Expert', 'Genius']);
});

test('static: items loaded correctly', () => {
  assert.strictEqual(items.length, 5);
});

test('static: story acts loaded correctly', () => {
  assert.strictEqual(storyActs.length, 4);
  assert.strictEqual(storyActs[0].title, 'Act I — Spark');
});

test('static: reward policy disabled', () => {
  assert.strictEqual(rewardPolicy.enabled, false);
  assert.strictEqual(rewardPolicy.policy, 'configurable');
});

// ── GET /api/missions ────────────────────────────────────────────────────────
test('GET /api/missions returns 12 missions', async () => {
  const r = await req('GET', '/api/missions');
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.length, 12);
});

test('GET /api/missions?wallet enriches quest states', async () => {
  const r = await req('GET', `/api/missions?wallet=${W}`);
  assert.strictEqual(r.status, 200);
  const easy = r.body.filter(m => m.tier === 'Easy');
  assert(easy.every(m => m.questState === 'available'));
  const normal = r.body.filter(m => m.tier === 'Normal');
  assert(normal.every(m => m.questState === 'locked'));
});

// ── POST /api/missions/start ─────────────────────────────────────────────────
test('start mission: available → in_progress', async () => {
  const token = await createAndAuth(W);
  const r = await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.questState, 'in_progress');
  assert.strictEqual(r.body.animation, 'quest_activate');
});

test('start mission: locked returns 400', async () => {
  const token = await createAndAuth(W);
  const r = await req('POST', '/api/missions/start', { wallet: W, missionId: 'N1' }, token);
  assert.strictEqual(r.status, 400);
  assert.strictEqual(r.body.code, 'MISSION_LOCKED');
});

test('start mission: missing fields returns 400', async () => {
  const token = await createAndAuth(W);
  const r = await req('POST', '/api/missions/start', { wallet: W }, token);
  assert.strictEqual(r.status, 400);
  assert.strictEqual(r.body.code, 'MISSING_FIELDS');
});

test('start mission: not found returns 404', async () => {
  const token = await createAndAuth(W);
  const r = await req('POST', '/api/missions/start', { wallet: W, missionId: 'ZZZ' }, token);
  assert.strictEqual(r.status, 404);
});

test('start mission: already in_progress is idempotent', async () => {
  const token = await createAndAuth(W);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  const r = await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.questState, 'in_progress');
});

// ── POST /api/missions/complete ──────────────────────────────────────────────
test('complete mission: awards DRX and animation', async () => {
  const token = await createAndAuth(W);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  const r = await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.questState, 'completed');
  assert.strictEqual(r.body.animation, 'reward_burst');
  assert.strictEqual(r.body.drx_earned, 100);
  assert.strictEqual(r.body.balance, 100);
});

test('complete mission: not started returns 400', async () => {
  const token = await createAndAuth(W);
  const r = await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  assert.strictEqual(r.status, 400);
  assert.strictEqual(r.body.code, 'NOT_STARTED');
});

test('complete mission: already completed returns 400', async () => {
  const token = await createAndAuth(W);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  const r = await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  assert.strictEqual(r.status, 400);
  assert.strictEqual(r.body.code, 'ALREADY_COMPLETED');
});

test('complete mission: locked returns 400', async () => {
  const token = await createAndAuth(W);
  const r = await req('POST', '/api/missions/complete', { wallet: W, missionId: 'N1' }, token);
  assert.strictEqual(r.status, 400);
  assert.strictEqual(r.body.code, 'MISSION_LOCKED');
});

// ── Tier progression ─────────────────────────────────────────────────────────
test('completing Easy tier unlocks Normal tier', async () => {
  const token = await createAndAuth(W);
  for (const id of ['E1', 'E2', 'E3']) {
    await req('POST', '/api/missions/start', { wallet: W, missionId: id }, token);
    await req('POST', '/api/missions/complete', { wallet: W, missionId: id }, token);
  }
  const r = await req('GET', `/api/missions?wallet=${W}`);
  const n1 = r.body.find(m => m.id === 'N1');
  assert.strictEqual(n1.questState, 'available');
});

test('completing Easy tier emits tier_unlock event', async () => {
  const token = await createAndAuth(W);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E2' }, token);
  await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E2' }, token);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E3' }, token);
  const r = await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E3' }, token);
  const unlock = r.body.unlocks.find(e => e.event === 'tier_unlock');
  assert(unlock, 'should have tier_unlock event');
  assert.strictEqual(unlock.tier, 'Normal');
});

test('completing Easy tier unlocks story Act II', async () => {
  const token = await createAndAuth(W);
  for (const id of ['E1', 'E2', 'E3']) {
    await req('POST', '/api/missions/start', { wallet: W, missionId: id }, token);
    await req('POST', '/api/missions/complete', { wallet: W, missionId: id }, token);
  }
  const r = await req('GET', `/api/story?wallet=${W}`);
  const act2 = r.body.find(a => a.id === 2);
  assert.strictEqual(act2.unlocked, true);
});

test('full tier chain: Easy → Normal → Expert → Genius', async () => {
  const token = await createAndAuth(W);
  const allIds = ['E1','E2','E3','N1','N2','N3','X1','X2','X3','G1','G2','G3'];
  for (const id of allIds) {
    await req('POST', '/api/missions/start', { wallet: W, missionId: id }, token);
    await req('POST', '/api/missions/complete', { wallet: W, missionId: id }, token);
  }
  const r = await req('GET', `/api/missions?wallet=${W}`);
  assert(r.body.every(m => m.questState === 'completed'));
  // Total DRX: 3*100 + 3*250 + 3*500 + 3*1000 = 5550
  const dash = await req('GET', `/api/dashboard/${W}`);
  assert.strictEqual(dash.body.balance, 5550);
  assert.strictEqual(dash.body.missionsCompleted, 12);
});

// ── Story endpoints ──────────────────────────────────────────────────────────
test('GET /api/story without wallet: Act I unlocked only', async () => {
  const r = await req('GET', '/api/story');
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.length, 4);
  assert.strictEqual(r.body[0].unlocked, true);
  assert.strictEqual(r.body[1].unlocked, false);
});

test('GET /api/story/:actId returns act content', async () => {
  const r = await req('GET', '/api/story/1');
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.id, 1);
  assert(r.body.content.length > 0);
});

test('GET /api/story/:actId locked act returns 403', async () => {
  const r = await req('GET', `/api/story/2?wallet=${W}`);
  assert.strictEqual(r.status, 403);
  assert.strictEqual(r.body.code, 'ACT_LOCKED');
});

test('GET /api/story/99 returns 404', async () => {
  const r = await req('GET', '/api/story/99');
  assert.strictEqual(r.status, 404);
});

// ── Dashboard endpoint ───────────────────────────────────────────────────────
test('GET /api/dashboard/:wallet returns player state', async () => {
  const r = await req('GET', `/api/dashboard/${W}`);
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.wallet, W);
  assert.strictEqual(r.body.balance, 0);
  assert.strictEqual(r.body.missionsCompleted, 0);
  assert.strictEqual(r.body.currentTier, 'Easy');
  assert.strictEqual(r.body.rewardPolicy.enabled, false);
});

test('dashboard reflects completed missions', async () => {
  const token = await createAndAuth(W);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  const r = await req('GET', `/api/dashboard/${W}`);
  assert.strictEqual(r.body.missionsCompleted, 1);
  assert.strictEqual(r.body.balance, 100);
});

// ── Items endpoints ──────────────────────────────────────────────────────────
test('GET /api/items returns all items', async () => {
  const r = await req('GET', '/api/items');
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.length, 5);
});

test('POST /api/items/buy: success', async () => {
  const token = await createAndAuth(W);
  // Give player some DRX first
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  // Balance: 100, buy I_COS_SKIN1 at 120 → fail
  const fail = await req('POST', '/api/items/buy/I_COS_SKIN1', { wallet: W }, token);
  assert.strictEqual(fail.status, 400);
  assert.strictEqual(fail.body.code, 'INSUFFICIENT_BALANCE');
  // Complete more missions
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E2' }, token);
  await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E2' }, token);
  // Balance: 200, buy I_COS_SKIN1 at 120 → success
  const ok = await req('POST', '/api/items/buy/I_COS_SKIN1', { wallet: W }, token);
  assert.strictEqual(ok.status, 200);
  assert.strictEqual(ok.body.balance, 80);
  assert.strictEqual(ok.body.animation, 'item_glow');
  assert(ok.body.inventory.includes('I_COS_SKIN1'));
});

test('POST /api/items/buy: item not found', async () => {
  const token = await createAndAuth(W);
  const r = await req('POST', '/api/items/buy/NOPE', { wallet: W }, token);
  assert.strictEqual(r.status, 404);
});

test('POST /api/items/buy: no wallet', async () => {
  const token = await createAndAuth(W);
  const r = await req('POST', '/api/items/buy/I_SEC_BOOST', {}, token);
  assert.strictEqual(r.status, 400);
});

// ── Wallet status ────────────────────────────────────────────────────────────
test('GET /api/status/:wallet returns state', async () => {
  const r = await req('GET', `/api/status/${W}`);
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.wallet, W);
  assert(Array.isArray(r.body.inventory));
  assert(typeof r.body.questStates === 'object');
});

// ── Withdraw ─────────────────────────────────────────────────────────────────
test('POST /api/withdraw: queues and zeroes balance', async () => {
  const token = await createAndAuth(W);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  const r = await req('POST', `/api/withdraw/${W}`);
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.request.amount, 100);
  assert.strictEqual(r.body.request.status, 'pending');
  const dash = await req('GET', `/api/dashboard/${W}`);
  assert.strictEqual(dash.body.balance, 0);
});

test('POST /api/withdraw: no balance returns 400', async () => {
  const r = await req('POST', `/api/withdraw/${W}`);
  assert.strictEqual(r.status, 400);
  assert.strictEqual(r.body.code, 'NO_BALANCE');
});

// ── Bridge ───────────────────────────────────────────────────────────────────
test('POST /api/bridge/drx-to-thr: success', async () => {
  const token = await createAndAuth(W);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  const r = await req('POST', '/api/bridge/drx-to-thr', { wallet: W, amount: 50, thrAddress: 'rTHR123' });
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.balance, 50);
  assert.strictEqual(r.body.request.type, 'drx-to-thr');
});

test('POST /api/bridge/drx-to-thr: insufficient balance', async () => {
  const r = await req('POST', '/api/bridge/drx-to-thr', { wallet: W, amount: 9999, thrAddress: 'rTHR123' });
  assert.strictEqual(r.status, 400);
  assert.strictEqual(r.body.code, 'INSUFFICIENT_BALANCE');
});

test('POST /api/bridge/thr-to-drx: queues request', async () => {
  const r = await req('POST', '/api/bridge/thr-to-drx', { thrAddress: 'rTHR123', amount: 100, wallet: W });
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.request.type, 'thr-to-drx');
});

// ── Reward policy ────────────────────────────────────────────────────────────
test('GET /api/reward-policy: returns policy', async () => {
  const r = await req('GET', '/api/reward-policy');
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.enabled, false);
  assert.strictEqual(r.body.policy, 'configurable');
});

// ── Error handling ───────────────────────────────────────────────────────────
test('404 for unknown endpoints', async () => {
  const r = await req('GET', '/api/nonexistent');
  assert.strictEqual(r.status, 404);
  assert.strictEqual(r.body.code, 'NOT_FOUND');
});

// ── Save / Resume ────────────────────────────────────────────────────────────
test('save/resume: persists player to disk', async () => {
  const token = await createAndAuth(W);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  // Check file exists
  const fpath = path.join(SAVES_DIR, `${W}.json`);
  assert(fs.existsSync(fpath), 'save file should exist');
  const data = JSON.parse(fs.readFileSync(fpath, 'utf8'));
  assert.strictEqual(data.wallet, W);
  assert.strictEqual(data.balance, 100);
  assert(data.completedMissions.includes('E1'));
  assert(data.lastSaved);
});

test('players are isolated between wallets', async () => {
  const token = await createAndAuth(W);
  await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  const r2 = await req('GET', `/api/dashboard/${W2}`);
  assert.strictEqual(r2.body.balance, 0);
  assert.strictEqual(r2.body.missionsCompleted, 0);
});

// ── Animation hooks in responses ─────────────────────────────────────────────
test('animation hooks present in mutation responses', async () => {
  const token = await createAndAuth(W);
  const start = await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' }, token);
  assert.strictEqual(start.body.event, 'mission_start');
  assert.strictEqual(start.body.animation, 'quest_activate');

  const complete = await req('POST', '/api/missions/complete', { wallet: W, missionId: 'E1' }, token);
  assert.strictEqual(complete.body.event, 'mission_complete');
  assert.strictEqual(complete.body.animation, 'reward_burst');
});

// ── Run ──────────────────────────────────────────────────────────────────────
run();
