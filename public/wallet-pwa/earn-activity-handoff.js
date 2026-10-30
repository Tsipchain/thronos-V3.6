// Keep the PWA's compact Earn card focused on balances.  The detailed history
// view belongs to the authenticated Earn dashboard, where it can show account
// and wallet-link state without copying sensitive data into the wallet UI.
document.addEventListener('click', (event) => {
  const button = event.target.closest('#openEarnCenterBtn');
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  window.location.assign('/earn?view=activity');
}, true);
