const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const WEB = path.join(__dirname, '..', '..', 'web');

describe('PWA assets', () => {
  it('manifest.json exists and is valid JSON', () => {
    const raw = fs.readFileSync(path.join(WEB, 'manifest.json'), 'utf8');
    const m = JSON.parse(raw);
    assert.equal(m.name, 'Crypto Hunters');
    assert.equal(m.display, 'standalone');
    assert.ok(m.icons.length >= 2);
    assert.equal(m.background_color, '#0b1020');
    assert.equal(m.theme_color, '#10b981');
    assert.ok(m.start_url);
  });

  it('service worker exists', () => {
    assert.ok(fs.existsSync(path.join(WEB, 'sw.js')));
    const sw = fs.readFileSync(path.join(WEB, 'sw.js'), 'utf8');
    assert.ok(sw.includes('install'), 'sw should handle install event');
    assert.ok(sw.includes('fetch'), 'sw should handle fetch event');
    assert.ok(sw.includes('activate'), 'sw should handle activate event');
  });

  it('icon files exist', () => {
    assert.ok(fs.existsSync(path.join(WEB, 'icons', 'icon-192.svg')));
    assert.ok(fs.existsSync(path.join(WEB, 'icons', 'icon-512.svg')));
  });

  it('index.html references manifest and service worker', () => {
    const html = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');
    assert.ok(html.includes('rel="manifest"'), 'should link manifest');
    assert.ok(html.includes('theme-color'), 'should have theme-color meta');
    assert.ok(html.includes('serviceWorker'), 'should register service worker');
    assert.ok(html.includes('apple-mobile-web-app-capable'), 'should have apple PWA meta');
  });

  it('index.html has mobile responsive breakpoints', () => {
    const html = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');
    assert.ok(html.includes('@media'), 'should have media queries');
    assert.ok(html.includes('max-width'), 'should have max-width breakpoint');
  });

  it('index.html has puzzle screens for E1 and E2', () => {
    const html = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');
    assert.ok(html.includes('puzzle-e1'), 'should have E1 puzzle screen');
    assert.ok(html.includes('puzzle-e2'), 'should have E2 puzzle screen');
    assert.ok(html.includes('SHA-256') || html.includes('sha256') || html.includes('SHA256'), 'should reference SHA-256');
  });

  it('manifest icons have correct sizes', () => {
    const m = JSON.parse(fs.readFileSync(path.join(WEB, 'manifest.json'), 'utf8'));
    const sizes = m.icons.map(i => i.sizes);
    assert.ok(sizes.includes('192x192'));
    assert.ok(sizes.includes('512x512'));
  });

  it('service worker caches app shell files', () => {
    const sw = fs.readFileSync(path.join(WEB, 'sw.js'), 'utf8');
    assert.ok(sw.includes('index.html') || sw.includes('./'), 'should cache index.html');
    assert.ok(sw.includes('manifest'), 'should cache manifest');
  });
});
