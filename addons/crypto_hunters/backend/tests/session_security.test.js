const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const crypto = require('node:crypto');

let BASE;
let server;

function req(method, path, body, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE);
    const opts = { method, hostname: url.hostname, port: url.port, path: url.pathname + (url.search || ''), headers: {} };
    if (body) opts.headers['Content-Type'] = 'application/json';
    if (token) opts.headers['Authorization'] = 'Bearer ' + token;
    const r = http.request(opts, res => {
      let d = '';
      res.on('data', c => (d += c));
      res.on('end', () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(d) }); }
        catch { resolve({ status: res.statusCode, body: d }); }
      });
    });
    r.on('error', reject);
    if (body) r.write(JSON.stringify(body));
    r.end();
  });
}

const CALLSIGN_A = 'sec_a_' + (Date.now() % 1e7);
const CALLSIGN_B = 'sec_b_' + (Date.now() % 1e7);
let TOKEN_A, TOKEN_B;

describe('Session security & ownership enforcement', () => {
  before(async () => {
    const { app } = require('../drx');
    server = app.listen(0);
    await new Promise(r => server.on('listening', r));
    BASE = `http://127.0.0.1:${server.address().port}`;
  });

  after(() => server?.close());

  // ── Session Token Creation ─────────────────────────────────

  it('POST /api/player/create returns sessionToken', async () => {
    const { status, body } = await req('POST', '/api/player/create', {
      callsign: CALLSIGN_A,
      hunterClass: 'hacker',
      avatar: { bodyType: 'athletic', face: 'angular', hair: 'cyber_cut', eyes: 'green', skinTone: 'medium', outfit: 'tactical_vest', accentColors: { primary: '#10b981', secondary: '#06b6d4' } }
    });
    assert.equal(status, 200);
    assert.ok(body.sessionToken, 'create should return sessionToken');
    assert.equal(typeof body.sessionToken, 'string');
    assert.ok(body.sessionToken.length >= 32);
    TOKEN_A = body.sessionToken;
  });

  it('POST /api/player/create returns sessionToken for second player', async () => {
    const { status, body } = await req('POST', '/api/player/create', {
      callsign: CALLSIGN_B,
      hunterClass: 'defender',
      avatar: { bodyType: 'slim', face: 'round', hair: 'braids', eyes: 'blue', skinTone: 'dark', outfit: 'lab_coat', accentColors: { primary: '#3b82f6', secondary: '#0f172a' } }
    });
    assert.equal(status, 200);
    assert.ok(body.sessionToken);
    TOKEN_B = body.sessionToken;
  });

  // ── Login ──────────────────────────────────────────────────

  it('POST /api/player/login returns sessionToken', async () => {
    const { status, body } = await req('POST', '/api/player/login', { callsign: CALLSIGN_A });
    assert.equal(status, 200);
    assert.ok(body.sessionToken);
    assert.equal(body.callsign, CALLSIGN_A);
  });

  it('POST /api/player/login with unknown player returns 404', async () => {
    const { status } = await req('POST', '/api/player/login', { callsign: 'noexist_' + (Date.now() % 1e7) });
    assert.equal(status, 404);
  });

  it('POST /api/player/login with invalid callsign returns 400', async () => {
    const { status } = await req('POST', '/api/player/login', { callsign: '!! invalid !!' });
    assert.equal(status, 400);
  });

  // ── Write route without token returns 401 ──────────────────

  it('POST /api/player/avatar without token returns 401', async () => {
    const { status, body } = await req('POST', '/api/player/avatar', {
      callsign: CALLSIGN_A,
      avatar: { bodyType: 'slim' }
    });
    assert.equal(status, 401);
    assert.equal(body.code, 'UNAUTHORIZED');
  });

  it('POST /api/player/equip without token returns 401', async () => {
    const { status } = await req('POST', '/api/player/equip', {
      callsign: CALLSIGN_A, slot: 'head', itemId: 'X'
    });
    assert.equal(status, 401);
  });

  it('POST /api/missions/start without token returns 401', async () => {
    const { status } = await req('POST', '/api/missions/start', {
      callsign: CALLSIGN_A, missionId: 'E1'
    });
    assert.equal(status, 401);
  });

  it('POST /api/story/choice without token returns 401', async () => {
    const { status } = await req('POST', '/api/story/choice', {
      callsign: CALLSIGN_A, chapterId: 'ch1', sceneId: 's2', choiceIndex: 0
    });
    assert.equal(status, 401);
  });

  // ── Invalid / expired token returns 401 ────────────────────

  it('POST /api/player/avatar with garbage token returns 401', async () => {
    const { status } = await req('POST', '/api/player/avatar', {
      callsign: CALLSIGN_A, avatar: { bodyType: 'slim' }
    }, 'totally_invalid_token_garbage');
    assert.equal(status, 401);
  });

  it('expired session returns 401', async () => {
    const { sessions, createSessionToken } = require('../drx');
    const token = createSessionToken(CALLSIGN_A);
    const hash = crypto.createHash('sha256').update(token).digest('hex');
    sessions[hash].expiresAt = Date.now() - 1000;
    const { status } = await req('POST', '/api/player/avatar', {
      callsign: CALLSIGN_A, avatar: { bodyType: 'slim' }
    }, token);
    assert.equal(status, 401);
  });

  // ── Cross-player mutation rejection (403) ──────────────────

  it('player B token cannot update player A avatar (403)', async () => {
    const { status, body } = await req('POST', '/api/player/avatar', {
      callsign: CALLSIGN_A,
      avatar: { bodyType: 'muscular' }
    }, TOKEN_B);
    assert.equal(status, 403);
    assert.equal(body.code, 'FORBIDDEN');
  });

  it('player A token cannot equip on player B (403)', async () => {
    const { status } = await req('POST', '/api/player/equip', {
      callsign: CALLSIGN_B, slot: 'head', itemId: 'I_SEC_BOOST'
    }, TOKEN_A);
    assert.equal(status, 403);
  });

  it('player A token cannot unequip on player B (403)', async () => {
    const { status } = await req('POST', '/api/player/unequip', {
      callsign: CALLSIGN_B, slot: 'head'
    }, TOKEN_A);
    assert.equal(status, 403);
  });

  it('player B token cannot make story choice for player A (403)', async () => {
    const { status } = await req('POST', '/api/story/choice', {
      callsign: CALLSIGN_A, chapterId: 'ch1', sceneId: 's2', choiceIndex: 0
    }, TOKEN_B);
    assert.equal(status, 403);
  });

  it('player B token cannot complete chapter for player A (403)', async () => {
    const { status } = await req('POST', '/api/story/complete-chapter', {
      callsign: CALLSIGN_A, chapterId: 'ch1'
    }, TOKEN_B);
    assert.equal(status, 403);
  });

  it('player B token cannot start mission for player A (403)', async () => {
    const { status } = await req('POST', '/api/missions/start', {
      callsign: CALLSIGN_A, missionId: 'E1'
    }, TOKEN_B);
    assert.equal(status, 403);
  });

  it('player B token cannot buy item for player A (403)', async () => {
    const { status } = await req('POST', '/api/items/buy/I_SEC_BOOST', {
      callsign: CALLSIGN_A
    }, TOKEN_B);
    assert.equal(status, 403);
  });

  // ── Valid token on own write route succeeds ────────────────

  it('player A token on own avatar update succeeds', async () => {
    const { status } = await req('POST', '/api/player/avatar', {
      callsign: CALLSIGN_A,
      avatar: { bodyType: 'muscular', face: 'sharp', hair: 'mohawk', eyes: 'amber', skinTone: 'olive', outfit: 'cyber_suit', accentColors: { primary: '#ff0000', secondary: '#00ff00' } }
    }, TOKEN_A);
    assert.equal(status, 200);
  });

  it('player A token can start and complete missions', async () => {
    const s = await req('POST', '/api/missions/start', { callsign: CALLSIGN_A, missionId: 'E1' }, TOKEN_A);
    assert.equal(s.status, 200);
    const c = await req('POST', '/api/missions/complete', { callsign: CALLSIGN_A, missionId: 'E1' }, TOKEN_A);
    assert.equal(c.status, 200);
  });

  // ── connect-wallet demo-disabled ───────────────────────────

  it('POST /api/player/connect-wallet returns 501 (demo-disabled)', async () => {
    const { status, body } = await req('POST', '/api/player/connect-wallet', {
      callsign: CALLSIGN_A, thrWallet: 'rFAKE_ADDRESS'
    });
    assert.equal(status, 501);
    assert.equal(body.code, 'DEMO_DISABLED');
  });

  // ── GET endpoints remain public ────────────────────────────

  it('GET /api/player/:callsign works without token', async () => {
    const { status } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN_A));
    assert.equal(status, 200);
  });

  it('GET /api/player/:callsign/sheet works without token', async () => {
    const { status } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN_A) + '/sheet');
    assert.equal(status, 200);
  });

  it('GET /api/avatar-options works without token', async () => {
    const { status } = await req('GET', '/api/avatar-options');
    assert.equal(status, 200);
  });

  it('GET /api/npcs works without token', async () => {
    const { status } = await req('GET', '/api/npcs');
    assert.equal(status, 200);
  });

  it('GET /api/characters works without token', async () => {
    const { status } = await req('GET', '/api/characters');
    assert.equal(status, 200);
  });
});
