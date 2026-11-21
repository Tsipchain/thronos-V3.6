import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
const buildConfig = require('../app.config.js');
const base = require('../app.json').expo;
const eas = JSON.parse(readFileSync(new URL('../eas.json', import.meta.url), 'utf8'));
const projectId = String(process.env.EAS_PROJECT_ID || '').trim();
const schemaOnly = process.env.NATIVE_CONFIG_SCHEMA_ONLY === '1';
const schemaProjectId = '00000000-0000-4000-8000-000000000001';

assert.match(projectId, /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  'Set EAS_PROJECT_ID to the genuine Expo project UUID before building.');
assert.ok(schemaOnly || projectId !== schemaProjectId,
  'The schema-only Expo project UUID cannot be used for a release build.');

const config = buildConfig({ config: base });
assert.equal(config.extra.eas.projectId, projectId);
assert.equal(config.android.allowBackup, false);
assert.equal(config.android.package, 'com.thronos.wallet');
assert.equal(config.ios.bundleIdentifier, 'com.thronos.wallet');
assert.deepEqual(config.runtimeVersion, { policy: 'appVersion' });

const plugins = new Map(config.plugins.map(entry => (
  Array.isArray(entry) ? [entry[0], entry[1] || {}] : [entry, {}]
)));
assert.equal(plugins.get('expo-secure-store')?.configureAndroidBackup, false);
assert.ok(plugins.has('expo-local-authentication'));
assert.equal(plugins.get('expo-build-properties')?.android?.usesCleartextTraffic, false);

assert.equal(eas.cli.requireCommit, true);
assert.equal(eas.build.preview.credentialsSource || eas.build.base.credentialsSource, 'remote');
assert.equal(eas.build.preview.distribution, 'internal');
assert.equal(eas.build.preview.android.buildType, 'apk');
assert.equal(eas.build.preview.ios.simulator, false);
assert.equal(eas.build.preview.env?.EXPO_PUBLIC_WALLET_FINANCIAL_ACTIONS ||
  eas.build.base.env.EXPO_PUBLIC_WALLET_FINANCIAL_ACTIONS, 'disabled');

console.log('native release configuration verified');
