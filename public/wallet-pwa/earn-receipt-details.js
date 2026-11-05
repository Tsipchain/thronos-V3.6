(function (root) {
  let activeDialog;
  function countdown(eta, now = Date.now()) {
    const seconds = Number(eta);
    if (!Number.isInteger(seconds) || seconds <= 0) return null;
    const left = Math.max(0, Math.ceil((seconds * 1000 - now) / 1000));
    const days = Math.floor(left / 86400);
    const hours = Math.floor(left % 86400 / 3600);
    const minutes = Math.floor(left % 3600 / 60);
    return { expired: left === 0, text: `${days}d ${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(left % 60).padStart(2, '0')}` };
  }

  async function open(entryId, options = {}) {
    if (activeDialog?.isConnected) activeDialog.close();
    const el = (tag, text) => { const node = document.createElement(tag); if (text != null) node.textContent = text; return node; };
    const greek = (options.language || document.documentElement.lang || '').startsWith('el');
    const tr = (en, gr) => greek ? gr : en;
    const unknown = tr('Not provided', 'Δεν έχει δοθεί');
    const date = value => Number.isInteger(Number(value)) && Number(value) > 0
      ? new Date(Number(value) * 1000).toLocaleString() : unknown;
    const dialog = el('dialog');
    activeDialog = dialog;
    dialog.setAttribute('aria-label', tr('Earn receipt details', 'Στοιχεία αμοιβής Earn'));
    dialog.style.cssText = 'width:min(520px,calc(100vw - 32px));max-height:85vh;overflow:auto;box-sizing:border-box;background:#111827;color:#e5e7eb;border:1px solid #53637e;border-radius:16px;padding:20px;font:14px system-ui';
    const head = el('div'); head.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:12px';
    const title = el('h2', tr('Earn receipt', 'Αμοιβή Earn')); title.style.cssText = 'font-size:19px;margin:0';
    const close = el('button', '×'); close.type = 'button'; close.setAttribute('aria-label', tr('Close receipt', 'Κλείσιμο στοιχείων'));
    close.style.cssText = 'background:transparent;color:inherit;border:0;font-size:28px;cursor:pointer';
    close.onclick = () => dialog.close(); head.append(title, close);
    const body = el('div', tr('Loading verified receipt…', 'Φόρτωση στοιχείων…'));
    body.style.marginTop = '16px'; dialog.append(head, body);
    let timer;
    dialog.addEventListener('close', () => { clearInterval(timer); dialog.remove(); });
    document.body.appendChild(dialog); dialog.showModal();
    try {
      const response = await fetch((options.base || '') + '/api/earn/history/' + encodeURIComponent(entryId), {
        credentials: 'include', headers: options.headers || {}, cache: 'no-store',
      });
      const data = await response.json();
      if (!response.ok || !data.ok || !data.entry) throw new Error('receipt_unavailable');
      if (!dialog.isConnected) return;
      const entry = data.entry;
      body.textContent = '';
      const fields = [
        [tr('Provider', 'Πάροχος'), entry.source],
        [tr('Reward', 'Αμοιβή'), String(entry.amount) + ' THC'],
        [tr('State', 'Κατάσταση'), entry.state],
        [tr('Provider status', 'Κατάσταση παρόχου'), entry.provider_status],
        [tr('Provider reference', 'Κωδικός παρόχου'), entry.source_ref],
        [tr('Receipt ID', 'Κωδικός εγγραφής'), entry.entry_id],
        [tr('Details', 'Περιγραφή'), entry.note],
        [tr('Received', 'Παραλήφθηκε'), date(entry.received_at)],
        [tr('Last updated', 'Ενημερώθηκε'), date(entry.updated_at)],
        [tr('Estimated clearance', 'Εκτίμηση εκκαθάρισης'), date(entry.estimated_clearance_at)],
        [tr('Cleared', 'Εκκαθαρίστηκε'), date(entry.cleared_at)],
        [tr('Settlement reference', 'Κωδικός διακανονισμού'), entry.settlement_ref],
      ];
      if (entry.reversal_reason) fields.push([tr('Reversal reason', 'Αιτία ακύρωσης'), entry.reversal_reason]);
      const list = el('dl'); list.style.cssText = 'display:grid;grid-template-columns:1fr 1.4fr;gap:10px;margin:0';
      for (const [label, value] of fields) {
        const term = el('dt', label); term.style.color = '#a5b4c8';
        const detail = el('dd', value == null || value === '' ? unknown : String(value));
        detail.style.cssText = 'margin:0;overflow-wrap:anywhere'; list.append(term, detail);
      }
      const clock = el('p'); clock.style.cssText = 'color:#f2c14e;padding:12px;background:#0b1220;border-radius:8px;line-height:1.5';
      const tick = () => {
        if (entry.state !== 'pending') {
          clock.textContent = tr('Recorded state: ', 'Καταγεγραμμένη κατάσταση: ') + entry.state;
          return;
        }
        const remaining = countdown(entry.estimated_clearance_at);
        clock.textContent = remaining == null
          ? tr('Awaiting provider clearance. No individual clearance date has been received.', 'Αναμονή εκκαθάρισης παρόχου. Δεν έχει παραληφθεί ημερομηνία για αυτή την αμοιβή.')
          : remaining.expired
          ? tr('Estimated time elapsed. Awaiting verified clearance.', 'Η εκτίμηση χρόνου έληξε. Αναμονή επιβεβαιωμένης εκκαθάρισης.')
          : tr('Estimated time remaining: ', 'Εκτιμώμενος χρόνος που απομένει: ') + remaining.text;
      };
      tick();
      if (entry.state === 'pending' && countdown(entry.estimated_clearance_at)) timer = setInterval(tick, 1000);
      body.append(list, clock);
      const events = Array.isArray(data.events) ? data.events : [];
      body.append(el('h3', tr('Recorded events', 'Καταγεγραμμένα συμβάντα')));
      for (const event of events) body.append(el('p', `${date(event.occurred_at)} · ${event.event_type} · ${event.state} · ${event.provider_status || ''}`));
      if (!events.length) body.append(el('p', tr('No additional audit events recorded.', 'Δεν έχουν καταγραφεί πρόσθετα συμβάντα.')));
      body.append(el('p', tr('A countdown never releases rewards. Provider payment to the treasury and a user payout are separate events.', 'Το χρονόμετρο δεν αποδεσμεύει αμοιβές. Η πληρωμή του παρόχου στο ταμείο και το payout χρήστη είναι ξεχωριστά συμβάντα.')));
    } catch (_) {
      if (dialog.isConnected) body.textContent = tr('Could not load this receipt. Close and try again.', 'Δεν φορτώθηκαν τα στοιχεία. Κλείσε και δοκίμασε ξανά.');
    }
  }
  root.ThronosEarnReceipts = { open, countdown };
})(window);
