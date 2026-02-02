// PR-5 + PR-2.2: Global Music Modal Module
// Handles session tracking + GPS telemetry sampling + Playlist Management

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

    // PR-2.2: Ensure URLs are prod-safe (never localhost)
    function normalizeMediaUrl(url) {
      if (!url) return '';
      let value = url.trim();
      // Strip localhost URLs
      value = value.replace(/^https?:\/\/localhost:\d+/i, '');
      // Use relative URL or origin-based URL
      if (value.startsWith('/')) {
        return value;
      }
      if (value.startsWith('http://') || value.startsWith('https://')) {
        try {
          const parsed = new URL(value);
          return parsed.pathname || '';
        } catch (e) {
          return value;
        }
      }
      return value;
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
      const modal = document.getElementById('musicModal');
      if (modal) {
        modal.classList.add('open');
      }
      // Load playlists when modal opens
      if (window.MusicPlaylist) {
        window.MusicPlaylist.loadPlaylists();
      }
      // Show current session status or start new one
      if (sessionActive && sessionId) {
        updateStatus(`Session started: ${sessionId}`);
      } else {
        startSession().catch(err => {
          console.warn('[MusicModal] Failed to start session', err);
          updateStatus('Failed to start session');
        });
      }
    }

    function close() {
      const modal = document.getElementById('musicModal');
      if (modal) {
        modal.classList.remove('open');
      }
      // Session continues in background when modal closes
      // User must click "End" to stop the session and GPS tracking
    }

    window.addEventListener('beforeunload', () => {
      stopGpsSampling();
      if (sessionActive) {
        endSession('page_unload');
      }
    });

    function isSessionActive() {
      return sessionActive;
    }

    function getSessionId() {
      return sessionId;
    }

    return {
      open,
      close,
      startSession,
      endSession,
      isSessionActive,
      getSessionId,
      normalizeMediaUrl,
      resolveMasterUrl,
      getAddress
    };
  })();
}

// PR-2.2: Music Playlist Management Module
if (typeof window.MusicPlaylist !== 'undefined') {
  console.log('[MusicPlaylist] Already loaded');
} else {
  window.MusicPlaylist = (function () {
    'use strict';

    const DEFAULT_PLAYLISTS = ['Favorites', 'Driving'];
    let playlists = [];
    let currentPlaylistId = null;

    function getAddress() {
      return window.MusicModal?.getAddress() ||
        (window.walletSession && typeof window.walletSession.getAddress === 'function'
          ? window.walletSession.getAddress()
          : '');
    }

    function resolveMasterUrl(path) {
      return window.MusicModal?.resolveMasterUrl(path) || path;
    }

    // PR-2.2: Normalize media URLs to be prod-safe
    function normalizeMediaUrl(url) {
      return window.MusicModal?.normalizeMediaUrl(url) || url;
    }

    async function loadPlaylists() {
      const wallet = getAddress();
      if (!wallet) {
        renderPlaylists([]);
        return [];
      }

      try {
        const resp = await fetch(resolveMasterUrl(`/api/music/playlists/${wallet}`));
        const data = await resp.json().catch(() => ({}));

        if (data.ok && data.playlists) {
          playlists = data.playlists;

          // PR-2.2: Create default playlists if none exist
          if (playlists.length === 0) {
            await ensureDefaultPlaylists(wallet);
          }

          renderPlaylists(playlists);
          return playlists;
        } else {
          // Empty state - create defaults
          await ensureDefaultPlaylists(wallet);
          return playlists;
        }
      } catch (e) {
        console.warn('[MusicPlaylist] Failed to load playlists', e);
        renderPlaylists([]);
        return [];
      }
    }

    async function ensureDefaultPlaylists(wallet) {
      for (const name of DEFAULT_PLAYLISTS) {
        const exists = playlists.some(p => p.name === name);
        if (!exists) {
          try {
            const resp = await fetch(resolveMasterUrl(`/api/music/playlists/${wallet}`), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name })
            });
            const data = await resp.json().catch(() => ({}));
            if (data.ok && data.playlist) {
              playlists.push(data.playlist);
            }
          } catch (e) {
            console.warn(`[MusicPlaylist] Failed to create default playlist: ${name}`, e);
          }
        }
      }
      renderPlaylists(playlists);
    }

    function renderPlaylists(items) {
      const container = document.getElementById('musicPlaylistsList');
      if (!container) return;

      if (!items || items.length === 0) {
        const wallet = getAddress();
        if (!wallet) {
          container.innerHTML = `
            <div style="color: #888; font-size: 11px; text-align: center; padding: 12px;">
              <span class="lang-en">Connect wallet to see playlists</span>
              <span class="lang-el">Σύνδεσε wallet για να δεις playlists</span>
            </div>`;
        } else {
          container.innerHTML = `
            <div style="color: #888; font-size: 11px; text-align: center; padding: 12px;">
              <span class="lang-en">No playlists yet. Create one!</span>
              <span class="lang-el">Δεν υπάρχουν playlists. Δημιούργησε ένα!</span>
            </div>`;
        }
        return;
      }

      const html = items.map(p => {
        const trackCount = p.tracks?.length || p.track_count || 0;
        const coverUrl = p.cover_url ? normalizeMediaUrl(p.cover_url) : null;
        const coverStyle = coverUrl
          ? `background-image: url('${coverUrl}'); background-size: cover;`
          : 'background: linear-gradient(135deg, #1a3a2a 0%, #0a1a10 100%);';

        return `
          <div class="music-playlist-item" data-id="${p.id}" onclick="window.MusicPlaylist.selectPlaylist('${p.id}')"
               style="display: flex; align-items: center; gap: 10px; padding: 8px; margin-bottom: 6px; background: rgba(0,255,102,0.05); border: 1px solid rgba(0,255,102,0.15); border-radius: 6px; cursor: pointer; transition: all 0.2s;">
            <div style="width: 40px; height: 40px; border-radius: 4px; flex-shrink: 0; ${coverStyle} display: flex; align-items: center; justify-content: center;">
              ${!coverUrl ? '🎵' : ''}
            </div>
            <div style="flex: 1; min-width: 0;">
              <div style="font-size: 12px; font-weight: bold; color: #0f6; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${p.name || 'Untitled'}</div>
              <div style="font-size: 10px; color: #888;">${trackCount} track${trackCount !== 1 ? 's' : ''}</div>
            </div>
            <button onclick="event.stopPropagation(); window.MusicPlaylist.deletePlaylist('${p.id}')"
                    style="padding: 4px 8px; background: rgba(255,0,0,0.15); border: 1px solid rgba(255,0,0,0.3); border-radius: 4px; color: #f66; font-size: 10px; cursor: pointer;">
              🗑️
            </button>
          </div>`;
      }).join('');

      container.innerHTML = html;
    }

    function showCreateDialog() {
      const dialog = document.getElementById('createPlaylistDialog');
      const input = document.getElementById('newPlaylistName');
      if (dialog) {
        dialog.style.display = 'block';
        if (input) {
          input.value = '';
          input.focus();
        }
      }
    }

    function hideCreateDialog() {
      const dialog = document.getElementById('createPlaylistDialog');
      if (dialog) {
        dialog.style.display = 'none';
      }
    }

    async function createPlaylist() {
      const input = document.getElementById('newPlaylistName');
      const name = (input?.value || '').trim();
      const wallet = getAddress();

      if (!name) {
        alert('Please enter a playlist name');
        return;
      }

      if (!wallet) {
        alert('Please connect your wallet first');
        return;
      }

      try {
        const resp = await fetch(resolveMasterUrl(`/api/music/playlists/${wallet}`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name })
        });
        const data = await resp.json().catch(() => ({}));

        if (data.ok && data.playlist) {
          playlists.push(data.playlist);
          renderPlaylists(playlists);
          hideCreateDialog();
          if (input) input.value = '';
        } else {
          alert(data.error || 'Failed to create playlist');
        }
      } catch (e) {
        console.warn('[MusicPlaylist] Failed to create playlist', e);
        alert('Failed to create playlist');
      }
    }

    async function deletePlaylist(playlistId) {
      const wallet = getAddress();
      if (!wallet || !playlistId) return;

      if (!confirm('Delete this playlist?')) return;

      try {
        const resp = await fetch(resolveMasterUrl(`/api/music/playlists/${wallet}/${playlistId}`), {
          method: 'DELETE'
        });
        const data = await resp.json().catch(() => ({}));

        if (data.ok) {
          playlists = playlists.filter(p => p.id !== playlistId);
          renderPlaylists(playlists);
        } else {
          alert(data.error || 'Failed to delete playlist');
        }
      } catch (e) {
        console.warn('[MusicPlaylist] Failed to delete playlist', e);
        alert('Failed to delete playlist');
      }
    }

    function selectPlaylist(playlistId) {
      currentPlaylistId = playlistId;
      const playlist = playlists.find(p => p.id === playlistId);
      if (playlist) {
        // Highlight selected playlist
        document.querySelectorAll('.music-playlist-item').forEach(el => {
          el.style.borderColor = el.dataset.id === playlistId
            ? 'rgba(0,255,102,0.6)'
            : 'rgba(0,255,102,0.15)';
        });

        // If tracks are available, could show them
        console.log('[MusicPlaylist] Selected playlist:', playlist.name, playlist);
      }
    }

    async function addTrackToPlaylist(playlistId, trackId) {
      const wallet = getAddress();
      if (!wallet || !playlistId || !trackId) return false;

      try {
        const resp = await fetch(resolveMasterUrl(`/api/music/playlists/${wallet}/${playlistId}/add`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ track_id: trackId })
        });
        const data = await resp.json().catch(() => ({}));

        if (data.ok) {
          // Refresh playlists to update track count
          loadPlaylists();
          return true;
        }
        return false;
      } catch (e) {
        console.warn('[MusicPlaylist] Failed to add track', e);
        return false;
      }
    }

    async function removeTrackFromPlaylist(playlistId, trackId) {
      const wallet = getAddress();
      if (!wallet || !playlistId || !trackId) return false;

      try {
        const resp = await fetch(resolveMasterUrl(`/api/music/playlists/${wallet}/${playlistId}/remove`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ track_id: trackId })
        });
        const data = await resp.json().catch(() => ({}));

        if (data.ok) {
          loadPlaylists();
          return true;
        }
        return false;
      } catch (e) {
        console.warn('[MusicPlaylist] Failed to remove track', e);
        return false;
      }
    }

    return {
      loadPlaylists,
      createPlaylist,
      deletePlaylist,
      selectPlaylist,
      addTrackToPlaylist,
      removeTrackFromPlaylist,
      showCreateDialog,
      hideCreateDialog,
      normalizeMediaUrl
    };
  })();
}

// ThronosMusic namespace for backward compatibility
window.ThronosMusic = window.ThronosMusic || {};
window.ThronosMusic.open = function () {
  const modal = document.getElementById('musicModal');
  if (modal) {
    modal.classList.add('open');
  }
  if (window.MusicModal && typeof window.MusicModal.open === 'function') {
    window.MusicModal.open();
  }
};

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('walletMusicBtn');
  if (btn) {
    btn.addEventListener('click', () => window.ThronosMusic.open());
  }
});
