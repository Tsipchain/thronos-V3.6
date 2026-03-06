import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { TokenBalance } from '../services/api';

export interface WalletState {
  isConnected: boolean;
  address: string | null;
  backedUp: boolean;
}

interface AppStore {
  // Wallet
  wallet: WalletState;
  setWallet: (w: Partial<WalletState>) => void;
  disconnect: () => void;

  // Tokens
  tokens: TokenBalance[];
  setTokens: (t: TokenBalance[]) => void;

  // Settings
  settings: {
    notifications: boolean;
    biometric: boolean;
    currency: string;
  };
  updateSettings: (s: Partial<AppStore['settings']>) => void;

  // Transaction history cache
  recentTxs: any[];
  setRecentTxs: (txs: any[]) => void;
}

export const useStore = create<AppStore>()(
  persist(
    (set) => ({
      wallet: { isConnected: false, address: null, backedUp: false },
      setWallet: (w) => set((s) => ({ wallet: { ...s.wallet, ...w } })),
      disconnect: () => set({ wallet: { isConnected: false, address: null, backedUp: false }, tokens: [], recentTxs: [] }),

      tokens: [],
      setTokens: (tokens) => set({ tokens }),

      settings: { notifications: true, biometric: false, currency: 'USD' },
      updateSettings: (s) => set((state) => ({ settings: { ...state.settings, ...s } })),

      recentTxs: [],
      setRecentTxs: (txs) => set({ recentTxs: txs }),
    }),
    {
      name: 'thronos-wallet-storage',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        wallet: state.wallet,
        settings: state.settings,
      }),
    },
  ),
);

export default useStore;
