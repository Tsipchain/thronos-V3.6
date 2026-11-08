import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../public/wallet-pwa/earn-provider-tabs.js', import.meta.url), 'utf8');
const earnPage = readFileSync(new URL('../templates/earn_beta.html', import.meta.url), 'utf8');

function webProviderFlow(context) {
  const start = earnPage.indexOf('  let promoOpening = false;');
  const end = earnPage.indexOf("  $('earn-surveys').addEventListener", start);
  assert.ok(start >= 0 && end > start);
  return vm.runInNewContext(`(() => { ${earnPage.slice(start, end)}; return openProviderWithPromo; })()`, context);
}

test('web promo opens the provider in the same tab and returns through browser Back', async () => {
  const events = [];
  let finishPromo;
  const flow = webProviderFlow({
    setStatus() {}, t: key => key,
    showPromo: () => { events.push('promo'); return new Promise(resolve => { finishPromo = resolve; }); },
    fetch: async () => { events.push('fetch'); return { ok: true, json: async () => ({ ok: true, url: 'https://provider.example/surveys' }) }; },
    earnAuthHeaders: () => ({}), URL,
    window: { location: { assign(url) { events.push('assign:' + url); } } },
  });
  const first = flow('cpx', '/api/earn/cpx/offerwall', 'Unavailable');
  const second = flow('cpx', '/api/earn/cpx/offerwall', 'Unavailable');
  assert.equal(await second, undefined);
  assert.deepEqual(events, ['promo']);
  finishPromo();
  await first;
  assert.deepEqual(events, ['promo', 'fetch', 'assign:https://provider.example/surveys']);
});

test('web provider error keeps Earn open for a retry', async () => {
  const statuses = [];
  let calls = 0;
  const flow = webProviderFlow({
    setStatus: (...args) => statuses.push(args), t: key => key,
    showPromo: async () => {},
    fetch: async () => { calls++; return { ok: false, json: async () => ({ error: 'provider_unavailable' }) }; },
    earnAuthHeaders: () => ({}), URL,
    window: { location: { assign() { assert.fail('must not navigate'); } } },
  });
  await flow('timewall', '/api/earn/timewall/offerwall', 'Unavailable');
  await flow('timewall', '/api/earn/timewall/offerwall', 'Unavailable');
  assert.equal(calls, 2);
  assert.deepEqual(statuses.at(-1), ['provider unavailable', true]);
});

function setup(blocked = false) {
  const opened = [];
  const window = {
    open(url, name) {
      if (blocked) return null;
      const navigations = [];
      const tab = {
        closed: false, opener: window, focuses: 0, navigations,
        focus() { this.focuses++; },
        close() { this.closed = true; },
        location: { replace(url) { navigations.push(url); } },
      };
      opened.push({ url, name, tab });
      return tab;
    },
  };
  vm.runInNewContext(source, { window, URL });
  return { tabs: window.ThronosEarnTabs, opened };
}

test('reserves a tab synchronously before requesting an authenticated URL', async () => {
  const { tabs, opened } = setup();
  let requests = 0;
  const promise = tabs.open('cpx', () => { requests++; return 'https://example.com/survey'; });
  assert.equal(opened.length, 1);
  assert.equal(requests, 0);
  assert.equal(opened[0].tab.opener, null);
  await promise;
  assert.equal(requests, 1);
  assert.deepEqual(opened[0].tab.navigations, ['https://example.com/survey']);
});

test('rapid taps share one pending request and one tab', async () => {
  const { tabs, opened } = setup();
  let resolveUrl;
  const url = new Promise(resolve => { resolveUrl = resolve; });
  const first = tabs.open('cpx', () => url);
  const second = tabs.open('cpx', () => assert.fail('duplicate URL request'));
  assert.equal(first, second);
  assert.equal(opened.length, 1);
  resolveUrl('https://example.com/survey');
  await first;
  assert.equal(opened[0].tab.navigations.length, 1);
});

test('cross-origin window properties are not inspected during promise resolution', async () => {
  const { tabs, opened } = setup();
  const pending = tabs.open('cpx', () => 'https://example.com/survey');
  Object.defineProperty(opened[0].tab, 'then', {
    get() { throw new Error('cross-origin property access'); },
  });
  assert.equal(await pending, true);
});

test('reopening an active survey only focuses it without navigating or refetching', async () => {
  const { tabs, opened } = setup();
  await tabs.open('timewall', () => 'https://example.com/start');
  await tabs.open('timewall', () => assert.fail('must preserve current survey'));
  assert.equal(opened.length, 1);
  assert.equal(opened[0].tab.focuses, 2);
  assert.deepEqual(opened[0].tab.navigations, ['https://example.com/start']);
});

test('providers have separate tabs and a closed tab can be reopened', async () => {
  const { tabs, opened } = setup();
  await tabs.open('cpx', () => 'https://example.com/cpx');
  await tabs.open('timewall', () => 'https://example.com/timewall');
  assert.notEqual(opened[0].name, opened[1].name);
  opened[0].tab.close();
  await tabs.open('cpx', () => 'https://example.com/new');
  assert.equal(opened.length, 3);
  assert.deepEqual(opened[2].tab.navigations, ['https://example.com/new']);
});

test('blocked popups keep Earn in place and do not request a provider URL', async () => {
  const { tabs, opened } = setup(true);
  await assert.rejects(tabs.open('cpx', () => assert.fail('must not fetch')), /popup_blocked/);
  assert.equal(opened.length, 0);
});

test('failed URL requests close the placeholder and allow retry', async () => {
  const { tabs, opened } = setup();
  await assert.rejects(tabs.open('pure', () => { throw new Error('earn_auth_required'); }), /earn_auth_required/);
  assert.equal(opened[0].tab.closed, true);
  await tabs.open('pure', () => 'https://example.com/retry');
  assert.equal(opened.length, 2);
});

test('unsafe URLs never reach a provider tab', async () => {
  for (const url of ['javascript:alert(1)', 'http://example.com/', 'https://user:password@example.com']) {
    const { tabs, opened } = setup();
    await assert.rejects(tabs.open('cpx', () => url), /provider_unavailable/);
    assert.equal(opened[0].tab.closed, true);
    assert.equal(opened[0].tab.navigations.length, 0);
  }
});

test('logout cancels in-flight navigation even if the fetch completes later', async () => {
  const { tabs, opened } = setup();
  let resolveUrl;
  const url = new Promise(resolve => { resolveUrl = resolve; });
  const first = tabs.open('cpx', () => url);
  tabs.reset();
  resolveUrl('https://example.com/old-account');
  await assert.rejects(first, /provider_cancelled/);
  assert.equal(opened[0].tab.navigations.length, 0);
  assert.equal(opened[0].tab.closed, true);
});

test('switching Earn accounts closes old tabs and requests the new identity', async () => {
  const { tabs, opened } = setup();
  await tabs.open('cpx', () => 'https://example.com/user-a', 'account-a');
  await tabs.open('cpx', () => 'https://example.com/user-b', 'account-b');
  assert.equal(opened.length, 2);
  assert.equal(opened[0].tab.closed, true);
  assert.deepEqual(opened[1].tab.navigations, ['https://example.com/user-b']);
});

test('old cancelled request cannot remove a newer provider tab', async () => {
  const { tabs, opened } = setup();
  let resolveUrl;
  const first = tabs.open('cpx', () => new Promise(resolve => { resolveUrl = resolve; }));
  await Promise.resolve();
  tabs.reset();
  await tabs.open('cpx', () => 'https://example.com/new');
  resolveUrl('https://example.com/old');
  await assert.rejects(first, /provider_cancelled/);
  await tabs.open('cpx', () => assert.fail('new survey must remain active'));
  assert.equal(opened.length, 2);
  assert.equal(opened[1].tab.closed, false);
});
