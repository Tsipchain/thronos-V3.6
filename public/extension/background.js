// Background service worker — handles WalletConnect relay polling and alarms

const API = 'https://api.thronoschain.org';

// Listen for messages from popup / content scripts
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'FETCH_BALANCE') {
    fetchBalance(msg.address).then(sendResponse).catch(e => sendResponse({ error: e.message }));
    return true; // async
  }
  if (msg.type === 'CHECK_WC_SESSION') {
    checkWcSession(msg.sessionId, msg.relay).then(sendResponse).catch(e => sendResponse({ error: e.message }));
    return true;
  }
  if (msg.type === 'PING') {
    sendResponse({ ok: true });
  }
});

async function fetchBalance(address) {
  const r = await fetch(`${API}/api/balances?address=${encodeURIComponent(address)}&show_zero=true`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function checkWcSession(sessionId, relay) {
  const base = (relay || API).replace(/\/$/, '');
  const r = await fetch(`${base}/api/wallet/wc/session/${encodeURIComponent(sessionId)}`);
  if (!r.ok) return { pending: false };
  return r.json();
}

// Keep-alive alarm every 25s so the service worker doesn't get killed mid-session
chrome.alarms.create('keepAlive', { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'keepAlive') {
    // no-op — just wakes the worker
  }
});
