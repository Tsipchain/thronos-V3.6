// Shared by the web Earn page and wallet PWA. Reserve a browser tab while the
// click still has user activation; never reload an in-progress provider survey.
(function (root) {
  const tabs = new Map();
  const sessionName = Math.random().toString(36).slice(2);
  let activeScope;

  function close(tab) {
    try { tab.close(); } catch (_) {}
  }

  function reset() {
    for (const entry of tabs.values()) close(entry.tab);
    tabs.clear();
    activeScope = undefined;
  }

  function open(provider, loadUrl, scope = 'session') {
    if (!/^(cpx|bitcotasks|pure|timewall)$/.test(provider)) {
      return Promise.reject(new Error('provider_unavailable'));
    }
    if (activeScope !== undefined && activeScope !== scope) reset();
    activeScope = scope;
    let entry = tabs.get(provider);
    if (entry) {
      let closed = true;
      try { closed = entry.tab.closed; } catch (_) {}
      if (!closed) {
        try { entry.tab.focus(); } catch (_) {}
        return entry.promise;
      }
    }

    // This must run before fetch/await, including on iOS Safari. Do not navigate
    // the Earn page as a popup fallback: that abandons the installed wallet.
    let tab;
    try { tab = root.open('', 'thronosEarn_' + sessionName + '_' + provider); } catch (_) {}
    if (!tab) return Promise.reject(new Error('popup_blocked'));
    try { tab.opener = null; } catch (_) {}
    entry = { tab, promise: null };
    tabs.set(provider, entry);
    entry.promise = Promise.resolve().then(loadUrl).then(rawUrl => {
      if (tabs.get(provider) !== entry || tab.closed) throw new Error('provider_cancelled');
      const url = new URL(rawUrl);
      if (url.protocol !== 'https:' || url.username || url.password) {
        throw new Error('provider_unavailable');
      }
      tab.location.replace(url.href);
      try { tab.focus(); } catch (_) {}
      // Do not resolve a promise with a cross-origin WindowProxy: promise
      // assimilation would read its forbidden `then` property.
      return true;
    }).catch(error => {
      if (tabs.get(provider) === entry) tabs.delete(provider);
      close(tab);
      throw error;
    });
    return entry.promise;
  }

  root.ThronosEarnTabs = { open, reset };
})(window);
