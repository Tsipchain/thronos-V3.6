// Background service worker for Thronos Wallet Extension

// Listen for installation
chrome.runtime.onInstalled.addListener(() => {
    console.log('Thronos Wallet Extension installed');

    // Set default settings - use production URL
    chrome.storage.local.get(['settings'], (result) => {
        if (!result.settings) {
            chrome.storage.local.set({
                settings: {
                    apiBase: 'https://thrchain.up.railway.app',
                    autoRefresh: true,
                    refreshInterval: 30000, // 30 seconds
                    notifications: true
                }
            });
        }
    });
});

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'getWallet') {
        chrome.storage.local.get(['thr_address', 'thr_secret'], (result) => {
            sendResponse({
                address: result.thr_address,
                secret: result.thr_secret,
                connected: !!(result.thr_address && result.thr_secret)
            });
        });
        return true; // Keep channel open for async response
    }

    if (request.action === 'setWallet') {
        chrome.storage.local.set({
            thr_address: request.address,
            thr_secret: request.secret
        }, () => {
            sendResponse({ success: true });
        });
        return true;
    }

    if (request.action === 'disconnect') {
        chrome.storage.local.remove(['thr_address', 'thr_secret'], () => {
            sendResponse({ success: true });
        });
        return true;
    }

    if (request.action === 'showNotification') {
        if (chrome.notifications) {
            chrome.notifications.create({
                type: 'basic',
                iconUrl: 'icons/icon48.png',
                title: request.title || 'Thronos Wallet',
                message: request.message,
                priority: 2
            });
        }
        sendResponse({ success: true });
        return true;
    }
});

// Auto-refresh wallet data
let refreshInterval = null;

chrome.storage.local.get(['settings'], (result) => {
    if (result.settings && result.settings.autoRefresh) {
        startAutoRefresh(result.settings.refreshInterval);
    }
});

function startAutoRefresh(interval) {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }

    refreshInterval = setInterval(() => {
        chrome.storage.local.get(['thr_address'], (result) => {
            if (result.thr_address) {
                // Notify popup to refresh if it's open
                chrome.runtime.sendMessage({ action: 'refresh' }).catch(() => {
                    // Popup not open, ignore
                });
            }
        });
    }, interval);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Listen for settings changes
chrome.storage.onChanged.addListener((changes, namespace) => {
    if (namespace === 'local' && changes.settings) {
        const newSettings = changes.settings.newValue;
        if (newSettings.autoRefresh) {
            startAutoRefresh(newSettings.refreshInterval);
        } else {
            stopAutoRefresh();
        }
    }
});
