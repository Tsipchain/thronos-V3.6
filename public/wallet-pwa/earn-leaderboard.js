(function (root) {
  function remaining(endsAt, serverNow, elapsedMs = 0) {
    if (![endsAt, serverNow, elapsedMs].every(Number.isFinite)) return null;
    return Math.max(0, Math.ceil(endsAt - serverNow - Math.max(0, elapsedMs) / 1000));
  }
  function clock(seconds) {
    if (seconds == null) return '—';
    return `${Math.floor(seconds / 86400)}d ${String(Math.floor(seconds % 86400 / 3600)).padStart(2, '0')}:${String(Math.floor(seconds % 3600 / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }

  function mount(container, options = {}) {
    if (container.__earnLeaderboard) return container.__earnLeaderboard.refresh();
    const greek = (options.language || document.documentElement.lang || '').startsWith('el');
    const tr = (en, gr) => greek ? gr : en;
    const el = (tag, text) => { const e = document.createElement(tag); if (text != null) e.textContent = text; return e; };
    const money = value => /^\d+\.\d{6}$/.test(String(value)) ? String(value) : '—';
    let data, sampledAt, stopped = false, loading = false;
    container.style.cssText = 'display:block;margin-top:16px;padding:16px;border:1px solid #675588;border-radius:14px;background:#15152d;color:#e5e7eb';
    container.textContent = '';
    const head = el('div'); head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:10px';
    const title = el('h3', tr('🏆 30-day leaderboard', '🏆 Κατάταξη 30 ημερών')); title.style.cssText = 'font-size:17px;margin:0';
    const refreshButton = el('button', tr('Refresh', 'Ανανέωση')); refreshButton.type = 'button';
    refreshButton.style.cssText = 'padding:7px 10px;border:1px solid #73638a;border-radius:8px;background:#25203b;color:inherit;cursor:pointer';
    head.append(title, refreshButton);
    const period = el('p'); period.style.cssText = 'font-size:12px;color:#bdc5da;line-height:1.5';
    const timer = el('p'); timer.style.cssText = 'font-size:19px;font-weight:700;color:#f2c14e;font-variant-numeric:tabular-nums';
    const stats = el('p'); stats.style.cssText = 'font-size:13px;line-height:1.7';
    const loyalty = el('p'); loyalty.style.cssText = 'padding:10px;border:1px solid #675588;border-radius:9px;font-size:13px;line-height:1.5';
    const rules = el('p', tr(
      'Verified provider receipts count toward the score. Pending THC is provisional; reversals are removed. Equal scores share a rank. Prizes will be announced separately.',
      'Μετρούν οι επαληθευμένες αμοιβές παρόχων. Τα pending THC δίνουν προσωρινή βαθμολογία· οι ακυρώσεις αφαιρούνται. Ίδια βαθμολογία σημαίνει ίδια θέση. Τα βραβεία θα ανακοινωθούν χωριστά.'));
    rules.style.cssText = 'font-size:12px;line-height:1.55;color:#aeb9d0';
    const notice = el('p', tr('Loading ranking…', 'Φόρτωση κατάταξης…')); notice.setAttribute('role', 'status'); notice.style.fontSize = '12px';
    const list = el('ol'); list.style.cssText = 'list-style:none;padding:0;margin:0';
    container.append(head, period, timer, loyalty, stats, rules, notice, list);

    function stop() {
      stopped = true; clearInterval(ticker); clearInterval(poller);
      document.removeEventListener('visibilitychange', onVisible);
      root.removeEventListener('focus', onVisible);
      delete container.__earnLeaderboard;
    }
    function tick() {
      if (!container.isConnected) { stop(); return; }
      if (!data) return;
      const seconds = remaining(data.ends_at, data.server_now, performance.now() - sampledAt);
      timer.textContent = data.phase === 'upcoming'
        ? tr('Cycle has not started yet.', 'Ο κύκλος δεν έχει ξεκινήσει ακόμη.')
        : seconds === 0 || data.phase === 'ended'
        ? tr('Cycle ended · results under review', 'Ο κύκλος ολοκληρώθηκε · έλεγχος αποτελεσμάτων')
        : tr('Time remaining: ', 'Απομένουν: ') + clock(seconds);
    }
    async function refresh() {
      if (stopped || loading || document.hidden) return;
      if (!container.isConnected) { stop(); return; }
      loading = true;
      try {
        const response = await fetch((options.base || '') + '/api/earn/leaderboard', {
          credentials: 'include', cache: 'no-store',
          headers: typeof options.headers === 'function' ? options.headers() : options.headers || {},
        });
        const result = await response.json();
        if (!response.ok || !result.ok || !Array.isArray(result.entries)) throw new Error('unavailable');
        if (stopped || !container.isConnected) return;
        data = result; sampledAt = performance.now();
        loyalty.textContent = data.loyalty?.vip
          ? tr('⭐ Wallet Loyalty VIP · Verified THR wallet link. Benefits will be announced separately.', '⭐ Wallet Loyalty VIP · Επιβεβαιωμένη σύνδεση THR wallet. Τα προνόμια θα ανακοινωθούν χωριστά.')
          : tr('Wallet Loyalty VIP · Link your THR wallet from Wallet PWA to activate your loyalty membership.', 'Wallet Loyalty VIP · Σύνδεσε το THR wallet σου από το Wallet PWA για να ενεργοποιηθεί η ιδιότητα loyalty.');
        loyalty.style.color = data.loyalty?.vip ? '#f2c14e' : '#bdc5da';
        period.textContent = [data.starts_at, data.ends_at].map(t => new Date(t * 1000).toLocaleString(greek ? 'el-GR' : 'en-GB', { timeZone: 'Europe/Athens' })).join(' → ') + tr(' · Athens time', ' · ώρα Ελλάδας');
        const score = data.your_score;
        stats.textContent = tr('Your rank: ', 'Η θέση σου: ') + (data.your_rank == null ? '—' : '#' + data.your_rank)
          + tr(' · Earners: ', ' · Συμμετέχοντες: ') + data.total_active
          + tr(' · Your score: ', ' · Η βαθμολογία σου: ') + money(score.total_earned) + ' THC'
          + tr(' · Pending: ', ' · Εκκρεμή: ') + money(score.pending_earned)
          + tr(' · Cleared: ', ' · Εκκαθαρισμένα: ') + money(score.cleared_earned);
        list.textContent = '';
        for (const entry of data.entries) {
          const row = el('li'); row.style.cssText = 'padding:11px 0;border-top:1px solid #ffffff20';
          const line = el('div'); line.style.cssText = 'display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-size:14px';
          line.append(el('strong', '#' + entry.rank + ' ' + entry.display_name + (entry.is_caller ? tr(' (You)', ' (Εσύ)') : '')),
            el('span', money(entry.total_earned) + ' THC'));
          const split = el('div', tr('Pending: ', 'Εκκρεμή: ') + money(entry.pending_earned)
            + tr(' · Cleared: ', ' · Εκκαθαρισμένα: ') + money(entry.cleared_earned)
            + tr(' · Receipts: ', ' · Αμοιβές: ') + entry.completions);
          split.style.cssText = 'font-size:11px;color:#abb6ce;margin-top:5px;line-height:1.5';
          if (entry.is_caller) row.style.color = '#77e4b6';
          row.append(line, split); list.appendChild(row);
        }
        notice.textContent = data.entries.length
          ? tr('Updated: ', 'Ενημερώθηκε: ') + new Date().toLocaleTimeString()
          : tr('No qualifying receipts in this cycle yet.', 'Δεν υπάρχουν ακόμη αμοιβές για αυτό τον κύκλο.');
        tick();
      } catch (_) {
        if (!stopped) notice.textContent = tr('Ranking could not refresh. Tap Refresh to retry.', 'Η κατάταξη δεν ανανεώθηκε. Πάτησε Ανανέωση για νέα προσπάθεια.');
      } finally { loading = false; }
    }
    refreshButton.onclick = refresh;
    function onVisible() { if (!document.hidden) refresh(); }
    document.addEventListener('visibilitychange', onVisible);
    root.addEventListener('focus', onVisible);
    const ticker = setInterval(tick, 1000);
    const poller = setInterval(refresh, 60000);
    container.__earnLeaderboard = { refresh, stop };
    return refresh();
  }
  root.ThronosEarnLeaderboard = { mount, remaining, clock };
})(window);
