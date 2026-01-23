// PR-5: Global Music Modal Module
// Handles session tracking + GPS telemetry sampling.

if (typeof window.MusicModal !== 'undefined') {
  console.log('[MusicModal] Already loaded');
} else {
  window.MusicModal = (function () {
    'use strict';

    let gpsIntervalId = null;
    let sessionId = null;
    let sessionActive = false;

    function masterBase() {
      const base = window.THRONOS_CONFIG && window.THRONOS_CONFIG.MASTER_PUBLIC_URL
        ? window.THRONOS_CONFIG.MASTER_PUBLIC_URL
        : '';
      return base.replace(/\/$/, '');
    }

    function resolveMasterUrl(path) {
      const base = masterBase();
      if (!base) return path;
      const normalized = path.startsWith('/') ? path : `/${path}`;
      return `${base}${normalized}`;
    }

    function getAddress() {
      return window.walletSession && typeof window.walletSession.getAddress === 'function'
        ? window.walletSession.getAddress()
        : '';
    }

    async function startSession() {
      if (sessionActive) return sessionId;
      const payload = {
        address: getAddress(),
        source: 'modal'
      };
      const resp = await fetch(resolveMasterUrl('/api/music/session/start'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || data.ok === false) {
        throw new Error(data.error || 'Failed to start music session');
      }
      sessionId = data.session_id || data.id || null;
      sessionActive = true;
      startGpsSampling();
      updateStatus(`Session started: ${sessionId || 'active'}`);
      return sessionId;
    }

    async function endSession(reason = 'modal_close') {
      if (!sessionActive) {
        stopGpsSampling();
        return null;
      }
      const payload = {
        session_id: sessionId,
        address: getAddress(),
        reason
      };
      try {
        await fetch(resolveMasterUrl('/api/music/session/end'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } catch (e) {
        console.warn('[MusicModal] Failed to end session', e);
      }
      sessionActive = false;
      const endedId = sessionId;
      sessionId = null;
      stopGpsSampling();
      updateStatus('Session ended');
      return endedId;
    }

    function startGpsSampling() {
      stopGpsSampling();
      if (!navigator.geolocation) {
        updateStatus('GPS unavailable in this browser.');
        return;
      }
      gpsIntervalId = setInterval(() => {
        navigator.geolocation.getCurrentPosition(
          (position) => {
            sendTelemetry(position);
          },
          (err) => {
            console.warn('[MusicModal] GPS error', err);
          },
          {
            enableHighAccuracy: true,
            maximumAge: 10000,
            timeout: 5000
          }
        );
      }, 5000);
    }

    function stopGpsSampling() {
      if (gpsIntervalId) {
        clearInterval(gpsIntervalId);
        gpsIntervalId = null;
      }
    }

    function sendTelemetry(position) {
      if (!position || !position.coords) return;
      const coords = position.coords;
      const payload = {
        session_id: sessionId,
        address: getAddress(),
        latitude: coords.latitude,
        longitude: coords.longitude,
        altitude: coords.altitude,
        speed: coords.speed,
        heading: coords.heading,
        timestamp: new Date().toISOString()
      };
      fetch(resolveMasterUrl('/api/music/gps_telemetry'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).catch(() => {
        // Best-effort telemetry.
      });
    }

    function updateStatus(message) {
      const el = document.getElementById('musicModalStatus');
      if (el) el.textContent = message || '';
    }

    function open() {
      startSession().catch(err => {
        console.warn('[MusicModal] Failed to start session', err);
        updateStatus('Failed to start session');
      });
    }

    function close() {
      endSession('modal_close');
    }

    window.addEventListener('beforeunload', () => {
      stopGpsSampling();
      if (sessionActive) {
        endSession('page_unload');
      }
    });

    return {
      open,
      close,
      startSession,
      endSession
    };
  })();
}
