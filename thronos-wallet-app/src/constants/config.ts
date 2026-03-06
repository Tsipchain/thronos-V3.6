// Thronos Wallet Configuration
// Points to the live Thronos blockchain nodes

export const CONFIG = {
  // Primary API (main node)
  API_URL: 'https://thronoschain.org',

  // Network
  NETWORK: 'mainnet',
  CHAIN_NAME: 'Thronos Chain',
  NATIVE_TOKEN: 'THR',

  // App
  APP_NAME: 'Thronos Wallet',
  APP_VERSION: '1.0.0',
  SUPPORT_EMAIL: 'support@thronos.io',

  // Deep-link scheme
  SCHEME: 'thronoswallet',

  // Cache durations (ms)
  BALANCE_CACHE_MS: 60_000,     // 1 minute
  PRICE_CACHE_MS: 300_000,      // 5 minutes
  TX_HISTORY_CACHE_MS: 120_000, // 2 minutes
};
