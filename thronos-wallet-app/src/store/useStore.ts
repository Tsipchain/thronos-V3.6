import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { TokenBalance } from '../services/api';

export interface WalletState {
  isConnected: boolean;
  address: string | null;
  backedUp: boolean;
  hasMnemonic: boolean;
  activeChain: 'thronos' | 'bitcoin' | 'ethereum';
  chainAddresses: {
    thronos: string | null;
    bitcoin: string | null;
    ethereum: string | null;
  };
}

interface T2EState {
  balance: number;
  totalEarned: number;
  multiplier: number;
  projectsCompleted: number;
}

interface MusicState {
  currentTrackId: string | null;
  isPlaying: boolean;
  queue: string[];
}

interface AppStore {
  // Wallet
  wallet: WalletState;
  setWallet: (w: Partial<WalletState>) => void;
  disconnect: () => void;
  setActiveChain: (chain: WalletState['activeChain']) => void;

  // Tokens
  tokens: TokenBalance[];
  setTokens: (t: TokenBalance[]) => void;

  // T2E (Train to Earn)
  t2e: T2EState;
  setT2E: (data: Partial<T2EState>) => void;

  // Settings
  settings: {
    notifications: boolean;
    biometric: boolean;
    currency: string;
    autoLockMinutes: number;
  };
  updateSettings: (s: Partial<AppStore['settings']>) => void;

  // Transaction history cache
  recentTxs: any[];
  setRecentTxs: (txs: any[]) => void;

  // Bridge history
  bridgeHistory: any[];
  setBridgeHistory: (txs: any[]) => void;

  // Music (Decent Music)
  music: MusicState;
  setMusic: (data: Partial<MusicState>) => void;
}

export const useStore = create<AppStore>()(
  persist(
    (set) => ({
      wallet: {
        isConnected: false,
        address: null,
        backedUp: false,
        hasMnemonic: false,
        activeChain: 'thronos',
        chainAddresses: {
          thronos: null,
          bitcoin: null,
          ethereum: null,
        },
      },
      setWallet: (w) => set((s) => ({
        wallet: {
          ...s.wallet,
          ...w,
          chainAddresses: w.chainAddresses
            ? { ...s.wallet.chainAddresses, ...w.chainAddresses }
            : s.wallet.chainAddresses,
        },
      })),
      disconnect: () => set({
        wallet: {
          isConnected: false,
          address: null,
          backedUp: false,
          hasMnemonic: false,
          activeChain: 'thronos',
          chainAddresses: { thronos: null, bitcoin: null, ethereum: null },
        },
        tokens: [],
        recentTxs: [],
        t2e: { balance: 0, totalEarned: 0, multiplier: 1.0, projectsCompleted: 0 },
        bridgeHistory: [],
      }),
      setActiveChain: (chain) => set((s) => ({
        wallet: {
          ...s.wallet,
          activeChain: chain,
          address: s.wallet.chainAddresses[chain] || s.wallet.address,
        },
      })),

      tokens: [],
      setTokens: (tokens) => set({ tokens }),

      t2e: { balance: 0, totalEarned: 0, multiplier: 1.0, projectsCompleted: 0 },
      setT2E: (data) => set((s) => ({ t2e: { ...s.t2e, ...data } })),

      settings: {
        notifications: true,
        biometric: false,
        currency: 'USD',
        autoLockMinutes: 5,
      },
      updateSettings: (s) => set((state) => ({ settings: { ...state.settings, ...s } })),

      recentTxs: [],
      setRecentTxs: (txs) => set({ recentTxs: txs }),

      bridgeHistory: [],
      setBridgeHistory: (txs) => set({ bridgeHistory: txs }),

      music: { currentTrackId: null, isPlaying: false, queue: [] },
      setMusic: (data) => set((s) => ({ music: { ...s.music, ...data } })),
    }),
    {
      name: 'thronos-wallet-storage',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        wallet: state.wallet,
        settings: state.settings,
        t2e: state.t2e,
      }),
    },
  ),
);

export default useStore;
