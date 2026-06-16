// Injected into page's main world — exposes window.thronos provider

(function () {
  'use strict';

  if (window.thronos) return; // already injected

  let _reqId = 0;
  function _sendToExt(msg) {
    return new Promise((resolve) => {
      const requestId = ++_reqId;
      const handler = (event) => {
        if (!event.data || !event.data.__thronos_ext_resp) return;
        if (event.data.requestId !== requestId) return;
        window.removeEventListener('message', handler);
        resolve(event.data.data);
      };
      window.addEventListener('message', handler);
      window.postMessage({ ...msg, __thronos_ext: true, requestId }, '*');
    });
  }

  const _listeners = {};

  window.thronos = {
    isThronos: true,
    version: '1.0.0',

    on(event, cb) {
      if (!_listeners[event]) _listeners[event] = [];
      _listeners[event].push(cb);
    },
    off(event, cb) {
      if (_listeners[event]) _listeners[event] = _listeners[event].filter(f => f !== cb);
    },
    emit(event, data) {
      (_listeners[event] || []).forEach(cb => { try { cb(data); } catch (_) {} });
    },

    async getAddress() {
      const r = await _sendToExt({ type: 'GET_ADDRESS' });
      return r && r.address ? r.address : null;
    },

    async signTransaction(txCore) {
      const r = await _sendToExt({ type: 'SIGN_TX', txCore });
      if (r && r.error) throw new Error(r.error);
      return r && r.signature;
    },

    async sendTransaction(txCore) {
      const r = await _sendToExt({ type: 'SEND_TX', txCore });
      if (r && r.error) throw new Error(r.error);
      return r;
    },

    async connect() {
      const r = await _sendToExt({ type: 'CONNECT' });
      return r;
    },
  };

  // Announce provider availability
  window.dispatchEvent(new CustomEvent('thronos#initialized'));
})();
