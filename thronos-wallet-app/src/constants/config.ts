// Thronos Wallet Configuration
// Points to the live Thronos blockchain nodes (Node1 master, Node2 replica)

export const CONFIG = {
  // Primary API — Node 1 (master)
  API_URL: 'https://api.thronoschain.org',

  // Replica API — Node 2 (replica, crosschain events, fallback)
  API_URL_REPLICA: 'https://ro.api.thronoschain.org',

  // Explorer
  EXPLORER_URL: 'https://explorer.thronoschain.org',

  // Network
  NETWORK: 'mainnet',
  CHAIN_NAME: 'Thronos Chain',
  NATIVE_TOKEN: 'THR',

  // App
  APP_NAME: 'Thronos Wallet',
  APP_VERSION: '1.1.0',
  SUPPORT_EMAIL: 'support@thronos.io',

  // Deep-link scheme
  SCHEME: 'thronoswallet',

  // Exchange Rates
  THR_BTC_RATE: 0.0001,     // 1 THR = 0.0001 BTC
  BTC_THR_RATE: 10_000,     // 1 BTC = 10,000 THR

  // BTC Pledge Vault — where new users send BTC fee for wallet creation
  BTC_PLEDGE_ADDRESS: '1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ',
  MIN_BTC_PLEDGE: 0.00001,  // minimum BTC to activate wallet

  // Token Registry (matches data/tokens_registry.json)
  TOKENS: {
    THR: { decimals: 6, chain: 'thronos', name: 'Thronos' },
    WBTC: { decimals: 8, chain: 'bitcoin', name: 'Wrapped Bitcoin' },
    L2E: { decimals: 6, chain: 'thronos', name: 'Learn to Earn' },
    T2E: { decimals: 6, chain: 'thronos', name: 'Train to Earn' },
    JAM: { decimals: 9, chain: 'thronos', name: 'tzamaikan' },
  },

  // Cross-Chain RPC Endpoints (from multichain_wallet.py)
  RPC: {
    ETH: 'https://eth.llamarpc.com',
    BSC: 'https://bsc-dataseed.binance.org',
    POLYGON: 'https://polygon-rpc.com',
    ARBITRUM: 'https://arb1.arbitrum.io/rpc',
    OPTIMISM: 'https://mainnet.optimism.io',
    SOLANA: 'https://api.mainnet-beta.solana.com',
    XRP: 'https://xrplcluster.com',
  },

  // Supported Cross-Chain Networks
  CHAINS: {
    thronos: { name: 'Thronos', symbol: 'THR', explorer: 'https://thronoschain.org' },
    bitcoin: { name: 'Bitcoin', symbol: 'BTC', explorer: 'https://blockstream.info' },
    ethereum: { name: 'Ethereum', symbol: 'ETH', explorer: 'https://etherscan.io' },
    bsc: { name: 'BSC', symbol: 'BNB', explorer: 'https://bscscan.com' },
    polygon: { name: 'Polygon', symbol: 'MATIC', explorer: 'https://polygonscan.com' },
    arbitrum: { name: 'Arbitrum', symbol: 'ARB', explorer: 'https://arbiscan.io' },
    avalanche: { name: 'Avalanche', symbol: 'AVAX', explorer: 'https://snowtrace.io' },
    base: { name: 'Base', symbol: 'ETH', explorer: 'https://basescan.org' },
    solana: { name: 'Solana', symbol: 'SOL', explorer: 'https://solscan.io' },
  },

  // Bridge Pairs
  BRIDGE_PAIRS: [
    { from: 'THR', to: 'WBTC', fee: 0.1, estimatedMinutes: 5, available: true },
    { from: 'WBTC', to: 'THR', fee: 0.1, estimatedMinutes: 5, available: true },
    { from: 'WBTC', to: 'BTC', fee: 0.15, estimatedMinutes: 15, available: true },
    { from: 'BTC', to: 'WBTC', fee: 0.15, estimatedMinutes: 15, available: true },
    { from: 'THR', to: 'ETH', fee: 0.2, estimatedMinutes: 10, available: true },
    { from: 'ETH', to: 'THR', fee: 0.2, estimatedMinutes: 10, available: true },
  ],

  // Phantom Network
  PHANTOM_GATEWAY: 'https://api.thronoschain.org',

  // Cache durations (ms)
  BALANCE_CACHE_MS: 60_000,     // 1 minute
  PRICE_CACHE_MS: 300_000,      // 5 minutes
  TX_HISTORY_CACHE_MS: 120_000, // 2 minutes
};
