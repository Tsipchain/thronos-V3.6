const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');

let BASE;
let server;

function req(method, path, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE);
    const opts = { method, hostname: url.hostname, port: url.port, path: url.pathname + (url.search || '') };
    if (body) opts.headers = { 'Content-Type': 'application/json' };
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

const CALLSIGN = 'test_hunter_' + Date.now();

describe('Phase 2A: Character creation, XP, story', () => {
  before(async () => {
    const { app } = require('../drx');
    server = app.listen(0);
    await new Promise(r => server.on('listening', r));
    BASE = `http://127.0.0.1:${server.address().port}`;
  });

  after(() => server?.close());

  // ── Characters ──────────────────────────────────────────────

  it('GET /api/characters returns unlocked characters', async () => {
    const { status, body } = await req('GET', '/api/characters');
    assert.equal(status, 200);
    assert.ok(Array.isArray(body));
    assert.ok(body.length >= 5);
    assert.ok(body.every(c => c.unlocked === true));
    assert.ok(body.every(c => c.id && c.name && c.stats));
  });

  it('each character has required stats', async () => {
    const { body } = await req('GET', '/api/characters');
    for (const c of body) {
      assert.ok(c.stats.hack !== undefined);
      assert.ok(c.stats.shield !== undefined);
      assert.ok(c.stats.intel !== undefined);
      assert.ok(c.stats.stamina !== undefined);
      assert.ok(c.stats.charisma !== undefined);
    }
  });

  // ── Player Creation ─────────────────────────────────────────

  it('POST /api/player/create: success', async () => {
    const { status, body } = await req('POST', '/api/player/create', {
      callsign: CALLSIGN,
      characterId: 'safa'
    });
    assert.equal(status, 200);
    assert.equal(body.callsign, CALLSIGN);
    assert.ok(body.character);
    assert.equal(body.character.id, 'safa');
    assert.ok(body.xp !== undefined);
  });

  it('POST /api/player/create: duplicate returns 409', async () => {
    const { status } = await req('POST', '/api/player/create', {
      callsign: CALLSIGN,
      characterId: 'niva'
    });
    assert.equal(status, 409);
  });

  it('POST /api/player/create: invalid callsign returns 400', async () => {
    const { status } = await req('POST', '/api/player/create', {
      callsign: '',
      characterId: 'safa'
    });
    assert.equal(status, 400);
  });

  it('POST /api/player/create: invalid character returns 400', async () => {
    const { status } = await req('POST', '/api/player/create', {
      callsign: 'another_' + Date.now(),
      characterId: 'nonexistent'
    });
    assert.equal(status, 400);
  });

  it('POST /api/player/create: locked character (zayne) returns 400', async () => {
    const { status } = await req('POST', '/api/player/create', {
      callsign: 'locked_test_' + Date.now(),
      characterId: 'zayne'
    });
    assert.equal(status, 400);
  });

  // ── Player Profile ──────────────────────────────────────────

  it('GET /api/player/:callsign returns profile with level', async () => {
    const { status, body } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN));
    assert.equal(status, 200);
    assert.equal(body.callsign, CALLSIGN);
    assert.ok(body.level !== undefined);
    assert.ok(body.character);
  });

  it('GET /api/player/:callsign: not found returns 404', async () => {
    const { status } = await req('GET', '/api/player/nonexistent_' + Date.now());
    assert.equal(status, 404);
  });

  // ── Wallet Connection ───────────────────────────────────────

  it('POST /api/player/connect-wallet: success', async () => {
    const { status, body } = await req('POST', '/api/player/connect-wallet', {
      callsign: CALLSIGN,
      thrWallet: 'rTHR_TEST_ADDRESS_123'
    });
    assert.equal(status, 200);
    assert.ok(body.thrWallet);
  });

  it('POST /api/player/connect-wallet: missing player returns 404', async () => {
    const { status } = await req('POST', '/api/player/connect-wallet', {
      callsign: 'nonexistent_' + Date.now(),
      thrWallet: 'rSOME'
    });
    assert.equal(status, 404);
  });

  // ── Story Chapters ──────────────────────────────────────────

  it('GET /api/story/chapters returns chapter list', async () => {
    const { status, body } = await req('GET', '/api/story/chapters?callsign=' + encodeURIComponent(CALLSIGN));
    assert.equal(status, 200);
    assert.ok(Array.isArray(body));
    assert.ok(body.length >= 1);
    assert.ok(body[0].id);
    assert.ok(body[0].title);
  });

  it('GET /api/story/chapter/ch1 returns chapter scenes', async () => {
    const { status, body } = await req('GET', '/api/story/chapter/ch1?callsign=' + encodeURIComponent(CALLSIGN));
    assert.equal(status, 200);
    assert.equal(body.id, 'ch1');
    assert.ok(Array.isArray(body.scenes));
    assert.ok(body.scenes.length > 0);
  });

  it('GET /api/story/chapter/nonexistent returns 404', async () => {
    const { status } = await req('GET', '/api/story/chapter/ch999?callsign=' + encodeURIComponent(CALLSIGN));
    assert.equal(status, 404);
  });

  // ── Story Choices ───────────────────────────────────────────

  it('POST /api/story/choice: valid choice applies effects', async () => {
    const { status, body } = await req('POST', '/api/story/choice', {
      callsign: CALLSIGN,
      chapterId: 'ch1',
      sceneId: 's2',
      choiceIndex: 0
    });
    assert.equal(status, 200);
    assert.ok(body.xp > 0);
    assert.ok(body.trust !== undefined);
    assert.ok(body.skills);
  });

  it('POST /api/story/choice: invalid chapter returns 404', async () => {
    const { status } = await req('POST', '/api/story/choice', {
      callsign: CALLSIGN,
      chapterId: 'ch999',
      sceneId: 's1',
      choiceIndex: 0
    });
    assert.equal(status, 404);
  });

  it('POST /api/story/choice: invalid scene returns 404', async () => {
    const { status } = await req('POST', '/api/story/choice', {
      callsign: CALLSIGN,
      chapterId: 'ch1',
      sceneId: 's999',
      choiceIndex: 0
    });
    assert.equal(status, 404);
  });

  it('POST /api/story/choice: invalid choiceIndex returns 400', async () => {
    const { status } = await req('POST', '/api/story/choice', {
      callsign: CALLSIGN,
      chapterId: 'ch1',
      sceneId: 's2',
      choiceIndex: 99
    });
    assert.equal(status, 400);
  });

  // ── Chapter Completion ──────────────────────────────────────

  it('POST /api/story/complete-chapter: success', async () => {
    const { status, body } = await req('POST', '/api/story/complete-chapter', {
      callsign: CALLSIGN,
      chapterId: 'ch1'
    });
    assert.equal(status, 200);
    assert.ok(body.xp > 0);
    assert.ok(body.storyCompleted.includes('ch1'));
  });

  it('POST /api/story/complete-chapter: already completed returns 400', async () => {
    const { status } = await req('POST', '/api/story/complete-chapter', {
      callsign: CALLSIGN,
      chapterId: 'ch1'
    });
    assert.equal(status, 400);
  });

  // ── XP and Level Verification ───────────────────────────────

  it('player XP accumulated from choices and chapter completion', async () => {
    const { body } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN));
    assert.ok(body.xp > 0, 'should have earned XP');
    assert.ok(body.level >= 1, 'should be at least level 1');
    assert.ok(Object.keys(body.skills).length > 0, 'should have skill progress');
  });

  // ── Backward Compat: existing endpoints still work ──────────

  it('missions endpoint works with callsign as wallet', async () => {
    const { status, body } = await req('POST', '/api/missions/start', {
      wallet: CALLSIGN,
      missionId: 'E1'
    });
    assert.ok(status === 200 || status === 400);
  });

  it('dashboard endpoint works with callsign', async () => {
    const { status, body } = await req('GET', '/api/dashboard/' + encodeURIComponent(CALLSIGN));
    assert.equal(status, 200);
    assert.ok(body.character || body.wallet || body.callsign);
  });
});
