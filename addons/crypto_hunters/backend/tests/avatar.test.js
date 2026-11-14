const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');

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

const CALLSIGN = 'av_' + (Date.now() % 1e8);
const CALLSIGN2 = 'av2_' + (Date.now() % 1e8);
const COMPAT_CALLSIGN = 'avc_' + (Date.now() % 1e8);
let TOKEN, TOKEN2, COMPAT_TOKEN;

const VALID_AVATAR = {
  bodyType: 'athletic',
  face: 'angular',
  hair: 'cyber_cut',
  eyes: 'green',
  skinTone: 'medium',
  outfit: 'tactical_vest',
  accentColors: { primary: '#10b981', secondary: '#06b6d4' }
};

describe('Avatar & Character Sheet system', () => {
  before(async () => {
    const { app } = require('../drx');
    server = app.listen(0);
    await new Promise(r => server.on('listening', r));
    BASE = `http://127.0.0.1:${server.address().port}`;
  });

  after(() => server?.close());

  // ── Avatar Options ──────────────────────────────────────────

  it('GET /api/avatar-options returns all customization categories', async () => {
    const { status, body } = await req('GET', '/api/avatar-options');
    assert.equal(status, 200);
    assert.ok(body.bodyTypes, 'should have bodyTypes');
    assert.ok(body.faces, 'should have faces');
    assert.ok(body.hairStyles, 'should have hairStyles');
    assert.ok(body.eyeColors, 'should have eyeColors');
    assert.ok(body.skinTones, 'should have skinTones');
    assert.ok(body.outfits, 'should have outfits');
    assert.ok(body.classes, 'should have classes');
    assert.ok(body.equipmentSlots, 'should have equipmentSlots');
    assert.ok(body.animationStates, 'should have animationStates');
    assert.ok(Array.isArray(body.bodyTypes));
    assert.ok(body.bodyTypes.length > 0);
    assert.ok(typeof body.classes === 'object' && !Array.isArray(body.classes));
    assert.ok(Object.keys(body.classes).length > 0);
  });

  // ── Player Creation with Avatar ─────────────────────────────

  it('POST /api/player/create with hunterClass + avatar succeeds', async () => {
    const { status, body } = await req('POST', '/api/player/create', {
      callsign: CALLSIGN,
      hunterClass: 'hacker',
      avatar: VALID_AVATAR
    });
    assert.equal(status, 200);
    assert.equal(body.callsign, CALLSIGN);
    assert.ok(body.hunterClass, 'should return hunterClass');
    assert.ok(body.avatar, 'should return avatar');
    assert.ok(body.assetId, 'should return assetId');
    assert.equal(body.avatar.bodyType, 'athletic');
    assert.ok(body.sessionToken, 'should return sessionToken');
    TOKEN = body.sessionToken;
  });

  it('POST /api/player/create with invalid hunterClass returns 400', async () => {
    const { status } = await req('POST', '/api/player/create', {
      callsign: 'bad_class_' + (Date.now() % 1e6),
      hunterClass: 'nonexistent_class',
      avatar: VALID_AVATAR
    });
    assert.equal(status, 400);
  });

  it('POST /api/player/create with invalid avatar field is handled gracefully', async () => {
    const cs = 'avbad_' + (Date.now() % 1e6);
    const { status } = await req('POST', '/api/player/create', {
      callsign: cs,
      hunterClass: 'hacker',
      avatar: { bodyType: 'INVALID_TYPE', face: 'angular', hair: 'cyber_cut', eyes: 'green', skinTone: 'medium', outfit: 'tactical_vest' }
    });
    // Should either accept with defaults or reject with 400
    assert.ok(status === 200 || status === 400, `expected 200 or 400, got ${status}`);
  });

  it('POST /api/player/create with characterId (backward compat) still works', async () => {
    const { status, body } = await req('POST', '/api/player/create', {
      callsign: COMPAT_CALLSIGN,
      characterId: 'safa'
    });
    assert.equal(status, 200);
    assert.equal(body.callsign, COMPAT_CALLSIGN);
    assert.ok(body.character, 'should return character for backward compat');
    assert.ok(body.sessionToken, 'should return sessionToken');
    COMPAT_TOKEN = body.sessionToken;
  });

  // ── Avatar Update ───────────────────────────────────────────

  it('POST /api/player/avatar updates appearance', async () => {
    const { status, body } = await req('POST', '/api/player/avatar', {
      callsign: CALLSIGN,
      avatar: { ...VALID_AVATAR, hair: 'mohawk', accentColors: { primary: '#ff0000', secondary: '#06b6d4' } }
    }, TOKEN);
    assert.equal(status, 200);
    assert.ok(body.avatar);
    assert.equal(body.avatar.hair, 'mohawk');
    assert.equal(body.avatar.accentColors.primary, '#ff0000');
  });

  it('POST /api/player/avatar without token returns 401', async () => {
    const { status } = await req('POST', '/api/player/avatar', {
      callsign: CALLSIGN,
      avatar: VALID_AVATAR
    });
    assert.equal(status, 401);
  });

  // ── Character Sheet ─────────────────────────────────────────

  it('GET /api/player/:callsign/sheet returns full character sheet', async () => {
    const { status, body } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN) + '/sheet');
    assert.equal(status, 200);
    assert.equal(body.callsign, CALLSIGN);
    assert.ok(body.avatar, 'sheet should include avatar');
    assert.ok(body.hunterClass, 'sheet should include hunterClass');
    assert.ok(body.equipment !== undefined, 'sheet should include equipment');
    assert.ok(body.animationState, 'sheet should include animationState');
    assert.ok(body.assetId, 'sheet should include assetId');
    assert.ok(body.level !== undefined, 'sheet should include level');
    assert.ok(body.xp !== undefined, 'sheet should include xp');
    assert.ok(body.skills !== undefined, 'sheet should include skills');
    assert.ok(body.trust !== undefined, 'sheet should include trust');
  });

  it('GET /api/player/:callsign/sheet for unknown player returns 404', async () => {
    const { status } = await req('GET', '/api/player/nonexistent_sheet/sheet');
    assert.equal(status, 404);
  });

  // ── NPCs ────────────────────────────────────────────────────

  it('GET /api/npcs returns canonical characters', async () => {
    const { status, body } = await req('GET', '/api/npcs');
    assert.equal(status, 200);
    assert.ok(Array.isArray(body));
    assert.ok(body.length >= 6, 'should have at least 6 NPCs');
    const names = body.map(n => n.handle || n.name);
    assert.ok(names.includes('SAfA'), 'should include SAfA');
    assert.ok(names.includes('Niva'), 'should include Niva');
    assert.ok(names.includes('Nato'), 'should include Nato');
  });

  it('GET /api/npcs includes locked characters (Zayne)', async () => {
    const { body } = await req('GET', '/api/npcs');
    const zayne = body.find(n => n.id === 'zayne');
    assert.ok(zayne, 'Zayne should be in NPCs');
  });

  // ── Equipment ───────────────────────────────────────────────
  // To test equip, we need balance. Start+complete E3 mission to get 100 DRX,
  // then buy I_SEC_BOOST (150). Need two missions. Start+complete E1 via direct
  // mission/start + mission/complete, then E3, then buy item.

  it('setup: earn DRX by completing missions E1 and E3', async () => {
    // Start and complete E1
    await req('POST', '/api/missions/start', { callsign: CALLSIGN, missionId: 'E1' }, TOKEN);
    const r1 = await req('POST', '/api/missions/complete', { callsign: CALLSIGN, missionId: 'E1' }, TOKEN);
    assert.equal(r1.status, 200);

    // Start and complete E3
    await req('POST', '/api/missions/start', { callsign: CALLSIGN, missionId: 'E3' }, TOKEN);
    const r3 = await req('POST', '/api/missions/complete', { callsign: CALLSIGN, missionId: 'E3' }, TOKEN);
    assert.equal(r3.status, 200);

    // Verify balance >= 150
    const { body } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN));
    assert.ok(body.balance >= 150, `balance should be >= 150, got ${body.balance}`);
  });

  it('setup: buy I_SEC_BOOST item', async () => {
    const { status, body } = await req('POST', '/api/items/buy/I_SEC_BOOST', { callsign: CALLSIGN }, TOKEN);
    assert.equal(status, 200);
    assert.ok(body.inventory.includes('I_SEC_BOOST'));
  });

  it('POST /api/player/equip: equips an item in inventory', async () => {
    const { status, body } = await req('POST', '/api/player/equip', {
      callsign: CALLSIGN,
      slot: 'tool',
      itemId: 'I_SEC_BOOST'
    }, TOKEN);
    assert.equal(status, 200);
    assert.ok(body.equipment);
    assert.equal(body.equipment.tool, 'I_SEC_BOOST');
  });

  it('POST /api/player/equip: invalid slot returns 400', async () => {
    const { status } = await req('POST', '/api/player/equip', {
      callsign: CALLSIGN,
      slot: 'wings',
      itemId: 'I_SEC_BOOST'
    }, TOKEN);
    assert.equal(status, 400);
  });

  it('POST /api/player/equip: item not in inventory returns 400', async () => {
    const { status } = await req('POST', '/api/player/equip', {
      callsign: CALLSIGN,
      slot: 'accessory',
      itemId: 'I_NONEXISTENT_ITEM'
    }, TOKEN);
    assert.equal(status, 400);
  });

  it('POST /api/player/unequip: unequips a slot', async () => {
    const { status, body } = await req('POST', '/api/player/unequip', {
      callsign: CALLSIGN,
      slot: 'tool'
    }, TOKEN);
    assert.equal(status, 200);
    assert.equal(body.equipment.tool, null);
  });

  it('POST /api/player/unequip: empty slot succeeds (no-op)', async () => {
    const { status, body } = await req('POST', '/api/player/unequip', {
      callsign: CALLSIGN,
      slot: 'head'
    }, TOKEN);
    assert.equal(status, 200);
    assert.equal(body.equipment.head, null);
  });

  // ── User Isolation ──────────────────────────────────────────

  it('setup: create second player', async () => {
    const { status, body } = await req('POST', '/api/player/create', {
      callsign: CALLSIGN2,
      hunterClass: 'defender',
      avatar: { ...VALID_AVATAR, hair: 'bald' }
    });
    assert.equal(status, 200);
    TOKEN2 = body.sessionToken;
  });

  it('player 1 avatar is not visible in player 2 sheet', async () => {
    const { body: s1 } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN) + '/sheet');
    const { body: s2 } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN2) + '/sheet');
    assert.notDeepStrictEqual(s1.avatar, s2.avatar);
    assert.notEqual(s1.assetId, s2.assetId);
  });

  it('player 2 cannot equip player 1 items', async () => {
    // Player 2 has no I_SEC_BOOST in inventory
    const { status } = await req('POST', '/api/player/equip', {
      callsign: CALLSIGN2,
      slot: 'tool',
      itemId: 'I_SEC_BOOST'
    }, TOKEN2);
    assert.equal(status, 400);
  });

  // ── Save / Resume ──────────────────────────────────────────

  it('player profile persists via getPlayer', async () => {
    const { body: before } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN) + '/sheet');
    // Re-fetch — data should be identical
    const { body: after } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN) + '/sheet');
    assert.equal(before.callsign, after.callsign);
    assert.deepStrictEqual(before.avatar, after.avatar);
    assert.equal(before.hunterClass, after.hunterClass);
    assert.equal(before.assetId, after.assetId);
  });

  // ── No Duplicate Ownership ─────────────────────────────────

  it('two players have distinct assetIds', async () => {
    const { body: p1 } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN) + '/sheet');
    const { body: p2 } = await req('GET', '/api/player/' + encodeURIComponent(CALLSIGN2) + '/sheet');
    assert.ok(p1.assetId);
    assert.ok(p2.assetId);
    assert.notEqual(p1.assetId, p2.assetId);
  });

  it('equipment from one player cannot be forged onto another', async () => {
    // Give CALLSIGN a tool again
    await req('POST', '/api/player/equip', {
      callsign: CALLSIGN,
      slot: 'tool',
      itemId: 'I_SEC_BOOST'
    }, TOKEN);
    // CALLSIGN2 tries to equip same item — should fail (not in their inventory)
    const { status } = await req('POST', '/api/player/equip', {
      callsign: CALLSIGN2,
      slot: 'tool',
      itemId: 'I_SEC_BOOST'
    }, TOKEN2);
    assert.equal(status, 400);
  });
});
