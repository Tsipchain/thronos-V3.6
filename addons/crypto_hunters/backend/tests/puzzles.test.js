const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const http = require('node:http');

let BASE;
let server;

function req(method, path, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE);
    const opts = { method, hostname: url.hostname, port: url.port, path: url.pathname };
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

describe('Puzzle endpoints', () => {
  const W = 'puzzle_test_' + Date.now();

  before(async () => {
    const app = require('../drx');
    server = app.listen(0);
    await new Promise(r => server.on('listening', r));
    BASE = `http://127.0.0.1:${server.address().port}`;
    await req('POST', '/api/missions/start', { wallet: W, missionId: 'E1' });
  });

  after(() => server?.close());

  // ── E1: Hello Hash ──────────────────────────────────────────────

  it('E1 check: correct hash accepted', async () => {
    const input = 'blockchain';
    const answer = crypto.createHash('sha256').update(input).digest('hex');
    const { status, body } = await req('POST', '/api/puzzles/e1/check', { wallet: W, input, answer });
    assert.equal(status, 200);
    assert.equal(body.correct, true);
  });

  it('E1 check: wrong hash rejected with hint', async () => {
    const { status, body } = await req('POST', '/api/puzzles/e1/check', { wallet: W, input: 'test', answer: 'wrong' });
    assert.equal(status, 200);
    assert.equal(body.correct, false);
    assert.ok(body.expected);
  });

  it('E1 check: missing fields returns 400', async () => {
    const { status } = await req('POST', '/api/puzzles/e1/check', { wallet: W });
    assert.equal(status, 400);
  });

  it('E1 complete: fails before 3 correct', async () => {
    const { status, body } = await req('POST', '/api/puzzles/e1/complete', { wallet: W });
    assert.equal(status, 400);
    assert.ok(body.needed !== undefined || body.error);
  });

  it('E1 complete: succeeds after 3 correct hashes', async () => {
    const words = ['satoshi', 'genesis', 'merkle'];
    for (const w of words) {
      const answer = crypto.createHash('sha256').update(w).digest('hex');
      const r = await req('POST', '/api/puzzles/e1/check', { wallet: W, input: w, answer });
      assert.equal(r.body.correct, true, `Hash for "${w}" should be correct`);
    }
    const { status, body } = await req('POST', '/api/puzzles/e1/complete', { wallet: W });
    assert.equal(status, 200);
    assert.ok(body.reward_drx || body.animation || body.event);
  });

  it('E1 complete: already completed returns 400', async () => {
    const { status } = await req('POST', '/api/puzzles/e1/complete', { wallet: W });
    assert.equal(status, 400);
  });

  // ── E2: Nonce Nudge ─────────────────────────────────────────────

  it('E2 generate: returns blockData and target', async () => {
    await req('POST', '/api/missions/start', { wallet: W, missionId: 'E2' });
    const { status, body } = await req('POST', '/api/puzzles/e2/generate', { wallet: W });
    assert.equal(status, 200);
    assert.ok(body.blockData);
    assert.ok(body.target);
    assert.ok(body.difficulty);
  });

  it('E2 check: wrong nonce rejected', async () => {
    const { status, body } = await req('POST', '/api/puzzles/e2/check', { wallet: W, nonce: 0 });
    if (body.correct) return; // unlikely but possible
    assert.equal(body.correct, false);
    assert.ok(body.hash);
  });

  it('E2 check: correct nonce accepted', async () => {
    // Brute-force the nonce (target is only 2 hex zeros = very easy)
    const gen = await req('POST', '/api/puzzles/e2/generate', { wallet: W });
    const { blockData, target } = gen.body;
    let nonce = 0;
    let hash;
    for (; nonce < 100000; nonce++) {
      hash = crypto.createHash('sha256').update(blockData + nonce.toString()).digest('hex');
      if (hash.startsWith(target)) break;
    }
    const { status, body } = await req('POST', '/api/puzzles/e2/check', { wallet: W, nonce });
    assert.equal(status, 200);
    assert.equal(body.correct, true);
  });

  it('E2 complete: succeeds after solving', async () => {
    const { status, body } = await req('POST', '/api/puzzles/e2/complete', { wallet: W });
    assert.equal(status, 200);
    assert.ok(body.reward_drx || body.animation || body.event);
  });

  it('E2 complete: already completed returns 400', async () => {
    const { status } = await req('POST', '/api/puzzles/e2/complete', { wallet: W });
    assert.equal(status, 400);
  });

  // ── E2 generate: missing wallet ──────────────────────────────────
  it('E2 generate: missing wallet returns 400', async () => {
    const { status } = await req('POST', '/api/puzzles/e2/generate', {});
    assert.equal(status, 400);
  });

  // ── Puzzle progress persists in player state ─────────────────────
  it('puzzle progress visible in dashboard', async () => {
    const { body } = await req('GET', '/api/dashboard/' + encodeURIComponent(W));
    assert.ok(body.completedMissions);
    assert.ok(body.completedMissions.includes('E1'));
    assert.ok(body.completedMissions.includes('E2'));
  });
});
