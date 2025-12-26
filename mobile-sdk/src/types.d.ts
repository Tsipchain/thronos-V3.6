/**
 * Thronos Mobile SDK TypeScript Definitions
 */

export interface ThronosConfig {
    apiUrl?: string;
    autoSave?: boolean;
    network?: 'mainnet' | 'testnet';
}

export interface Wallet {
    address: string;
    secret: string;
}

export interface Token {
    symbol: string;
    name: string;
    balance: number;
    decimals: number;
    color: string;
    logo?: string;
}

export interface TokensResponse {
    address: string;
    tokens: Token[];
    last_updated: string;
}

export interface Transaction {
    from: string;
    to: string;
    amount: number;
    token: string;
    timestamp: string;
    hash: string;
    status: 'pending' | 'confirmed' | 'failed';
}

export interface TransactionRequest {
    from: string;
    to: string;
    amount: number;
    token: string;
    secret: string;
}

export interface TransactionResponse {
    success: boolean;
    transaction: Transaction;
}

export interface SwapQuote {
    rate: number;
    amount_out: number;
    fee: number;
}

export interface SwapRequest {
    from: string;
    fromToken: string;
    toToken: string;
    amount: number;
    secret: string;
}

export interface PledgeInfo {
    pledged_amount: number;
    rewards: number;
    apr: number;
}

export interface AICredits {
    credits: number;
    used: number;
    remaining: number;
}

export interface NetworkStatus {
    status: 'online' | 'offline';
    blockHeight: number;
    peers: number;
}

export interface TokenPrice {
    symbol: string;
    price: number;
    change_24h: number;
}

export default class ThronosSDK {
    constructor(config?: ThronosConfig);

    createWallet(): Promise<Wallet>;
    importWallet(address: string, secret: string): Promise<Wallet>;
    getWallet(): Promise<Wallet | null>;
    isConnected(): Promise<boolean>;
    getAddress(): Promise<string | null>;

    getBalances(address?: string, showZero?: boolean): Promise<TokensResponse>;
    getTokenBalance(tokenSymbol: string, address?: string): Promise<number>;

    sendTransaction(to: string, amount: number, token?: string): Promise<TransactionResponse>;
    getTransactionHistory(address?: string, limit?: number): Promise<Transaction[]>;

    disconnect(): Promise<void>;

    signMessage(message: string): Promise<string>;
    verifySignature(message: string, signature: string, address: string): Promise<boolean>;
}

export class ThronosWallet {
    constructor(config: ThronosConfig);

    create(): Promise<Wallet>;
    import(address: string, secret: string): Promise<Wallet>;
    save(address: string, secret: string): Promise<void>;
    get(): Promise<Wallet | null>;
    isConnected(): Promise<boolean>;
    disconnect(): Promise<void>;
    signMessage(message: string, secret: string): Promise<string>;
    verifySignature(message: string, signature: string, address: string): Promise<boolean>;
    export(): Promise<Wallet>;
    getQRData(): Promise<string>;
}

export class ThronosAPI {
    constructor(config: ThronosConfig);

    getTokens(address: string, showZero?: boolean): Promise<TokensResponse>;
    sendTransaction(transaction: TransactionRequest): Promise<TransactionResponse>;
    getTransactionHistory(address: string, limit?: number): Promise<Transaction[]>;
    getNetworkStatus(): Promise<NetworkStatus>;
    getTokenPrice(symbol: string): Promise<TokenPrice>;

    getSwapQuote(fromToken: string, toToken: string, amount: number): Promise<SwapQuote>;
    executeSwap(swapDetails: SwapRequest): Promise<TransactionResponse>;

    getPledgeInfo(address: string): Promise<PledgeInfo>;
    pledgeTokens(pledgeDetails: any): Promise<TransactionResponse>;
    unpledgeTokens(unpledgeDetails: any): Promise<TransactionResponse>;

    getAICredits(address: string): Promise<AICredits>;
    sendAIMessage(messageDetails: any): Promise<any>;

    getIoTNodeStatus(nodeId: string): Promise<any>;
    registerIoTNode(nodeDetails: any): Promise<any>;

    getBridgeStatus(): Promise<any>;
    bridgeBTC(bridgeDetails: any): Promise<TransactionResponse>;
    bridgeWBTC(bridgeDetails: any): Promise<TransactionResponse>;

    getContract(contractAddress: string): Promise<any>;
    deployContract(contractDetails: any): Promise<any>;
    callContract(callDetails: any): Promise<any>;
}

export const Thronos: typeof ThronosSDK;
