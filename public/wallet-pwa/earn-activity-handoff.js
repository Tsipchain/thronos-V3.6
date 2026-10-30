// The PWA owns its Earn detail view.  Do not navigate to the web dashboard:
// an authenticated wallet session must stay in the installed PWA surface.
document.addEventListener('click', (event) => {
  const button = event.target.closest('#openEarnCenterBtn');
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  if (typeof window.__thronosOpenEarnActivity === 'function') {
    window.__thronosOpenEarnActivity();
  }
}, true);
