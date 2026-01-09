// PR-5: Shared Music/Playlists Module
// Used by both wallet widget and full wallet page
// Implements offline-first architecture with localStorage caching

const MusicModule = (function() {
    'use strict';

    // Private state
    let currentAddress = null;
    let library = [];
    let playlists = [];
    let selectedPlaylist = null;

    // Cache keys
    const CACHE_PREFIX = 'music_cache:';
    const getCacheKey = (addr, type) => `${CACHE_PREFIX}${addr}:${type}`;

    // Initialize module with address
    function init(address) {
        if (!address) {
            console.error('[MusicModule] No address provided');
            return Promise.reject(new Error('Address required'));
        }

        currentAddress = address;

        // Load from cache first (offline support)
        loadFromCache();

        // Fetch fresh data in background
        return Promise.all([
            fetchLibrary(address),
            fetchPlaylists(address)
        ]).then(() => {
            console.log('[MusicModule] Initialized for', address);
        }).catch(err => {
            console.error('[MusicModule] Failed to fetch data:', err);
            // Graceful degradation - use cached data
        });
    }

    // Load from localStorage (offline support)
    function loadFromCache() {
        try {
            const cachedLibrary = localStorage.getItem(getCacheKey(currentAddress, 'library'));
            const cachedPlaylists = localStorage.getItem(getCacheKey(currentAddress, 'playlists'));

            if (cachedLibrary) {
                const data = JSON.parse(cachedLibrary);
                library = data.library || [];
                console.log('[MusicModule] Loaded', library.length, 'tracks from cache');
            }

            if (cachedPlaylists) {
                const data = JSON.parse(cachedPlaylists);
                playlists = data.playlists || [];
                console.log('[MusicModule] Loaded', playlists.length, 'playlists from cache');
            }
        } catch (e) {
            console.error('[MusicModule] Failed to load cache:', e);
        }
    }

    // Save to localStorage
    function saveToCache() {
        try {
            localStorage.setItem(getCacheKey(currentAddress, 'library'), JSON.stringify({
                library: library,
                last_synced: new Date().toISOString()
            }));

            localStorage.setItem(getCacheKey(currentAddress, 'playlists'), JSON.stringify({
                playlists: playlists,
                last_synced: new Date().toISOString()
            }));
        } catch (e) {
            console.error('[MusicModule] Failed to save cache:', e);
        }
    }

    // Fetch library from API
    async function fetchLibrary(address) {
        try {
            const response = await fetch(`/api/music/library?address=${encodeURIComponent(address)}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            if (data.ok) {
                library = data.library || [];
                saveToCache();
                console.log('[MusicModule] Fetched', library.length, 'tracks');
            }
        } catch (err) {
            console.error('[MusicModule] Failed to fetch library:', err);
            throw err;
        }
    }

    // Fetch playlists from API
    async function fetchPlaylists(address) {
        try {
            const response = await fetch(`/api/music/playlists?address=${encodeURIComponent(address)}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            if (data.ok) {
                playlists = data.playlists || [];
                saveToCache();
                console.log('[MusicModule] Fetched', playlists.length, 'playlists');
            }
        } catch (err) {
            console.error('[MusicModule] Failed to fetch playlists:', err);
            throw err;
        }
    }

    // Create new playlist
    async function createPlaylist(name, visibility = 'private') {
        if (!currentAddress) {
            throw new Error('Not initialized');
        }

        const response = await fetch('/api/music/playlist/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                address: currentAddress,
                action: 'create',
                name: name,
                visibility: visibility
            })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to create playlist');
        }

        const data = await response.json();

        // Refetch playlists
        await fetchPlaylists(currentAddress);

        return data;
    }

    // Add track to playlist
    async function addTrackToPlaylist(playlistId, trackId, position) {
        if (!currentAddress) {
            throw new Error('Not initialized');
        }

        const payload = {
            address: currentAddress,
            action: 'add_track',
            playlist_id: playlistId,
            track_id: trackId
        };

        if (position !== undefined && position !== null) {
            payload.position = position;
        }

        const response = await fetch('/api/music/playlist/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to add track');
        }

        const data = await response.json();

        // Refetch playlists
        await fetchPlaylists(currentAddress);

        return data;
    }

    // Remove track from playlist
    async function removeTrackFromPlaylist(playlistId, trackId) {
        if (!currentAddress) {
            throw new Error('Not initialized');
        }

        const response = await fetch('/api/music/playlist/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                address: currentAddress,
                action: 'remove_track',
                playlist_id: playlistId,
                track_id: trackId
            })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to remove track');
        }

        const data = await response.json();

        // Refetch playlists
        await fetchPlaylists(currentAddress);

        return data;
    }

    // Reorder playlist tracks
    async function reorderPlaylist(playlistId, trackIds) {
        if (!currentAddress) {
            throw new Error('Not initialized');
        }

        const response = await fetch('/api/music/playlist/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                address: currentAddress,
                action: 'reorder',
                playlist_id: playlistId,
                track_ids: trackIds
            })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to reorder playlist');
        }

        const data = await response.json();

        // Refetch playlists
        await fetchPlaylists(currentAddress);

        return data;
    }

    // Refresh data
    async function refresh() {
        if (!currentAddress) return;

        await Promise.all([
            fetchLibrary(currentAddress),
            fetchPlaylists(currentAddress)
        ]);
    }

    // Getters
    function getLibrary() {
        return library;
    }

    function getPlaylists() {
        return playlists;
    }

    function getPlaylist(playlistId) {
        return playlists.find(p => p.playlist_id === playlistId);
    }

    function getTrack(trackId) {
        return library.find(t => t.track_id === trackId);
    }

    // Public API
    return {
        init,
        refresh,
        getLibrary,
        getPlaylists,
        getPlaylist,
        getTrack,
        createPlaylist,
        addTrackToPlaylist,
        removeTrackFromPlaylist,
        reorderPlaylist
    };
})();

// Export for module systems (optional)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MusicModule;
}
