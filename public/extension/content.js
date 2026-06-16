// Content script — injects the Thronos provider into web pages

(function () {
  'use strict';

  // Inject the provider script into the page's main world
  const s = document.createElement('script');
  s.src = chrome.runtime.getURL('inject.js');
  s.onload = function () { this.remove(); };
  (document.head || document.documentElement).appendChild(s);

  // Relay messages from page ↔ extension background
  window.addEventListener('message', (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.__thronos_ext !== true) return;

    chrome.runtime.sendMessage(event.data, (response) => {
      window.postMessage({
        __thronos_ext_resp: true,
        requestId: event.data.requestId,
        data: response,
      }, '*');
    });
  });
})();
