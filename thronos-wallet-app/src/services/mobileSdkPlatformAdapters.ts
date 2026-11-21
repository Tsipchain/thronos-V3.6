// Production adapters for the JavaScript Mobile SDK when embedded in the
// actual Expo Android/iOS host. Key material is generated locally and stored
// by the OS Keychain/Keystore. No device identifier participates in the key.

import * as SecureStore from 'expo-secure-store';
import * as LocalAuthentication from 'expo-local-authentication';
import { secp256k1 } from '@noble/curves/secp256k1';

const SDK_STORAGE_KEY = 'thr_mobile_sdk_storage_key_v2';
let storageKeyRequest: Promise<string> | null = null;

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes).map(value => value.toString(16).padStart(2, '0')).join('');
}

async function loadOrCreateMobileSdkStorageKey(): Promise<string> {
  const options: SecureStore.SecureStoreOptions = {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    requireAuthentication: true,
    authenticationPrompt: 'Unlock Thronos secure wallet storage',
  };
  const existing = await SecureStore.getItemAsync(SDK_STORAGE_KEY, options);
  if (existing) return existing;

  const generated = bytesToHex(secp256k1.utils.randomPrivateKey());
  await SecureStore.setItemAsync(SDK_STORAGE_KEY, generated, options);
  return generated;
}

export async function getOrCreateMobileSdkStorageKey(): Promise<string> {
  // Serialize first enrollment inside the JS runtime so concurrent wallet
  // initialization cannot encrypt records under different newly-created keys.
  if (!storageKeyRequest) storageKeyRequest = loadOrCreateMobileSdkStorageKey();
  try {
    return await storageKeyRequest;
  } finally {
    storageKeyRequest = null;
  }
}

export async function approveMobileSdkOperation(request: {
  reason: string;
  allowDevicePasscode?: boolean;
}): Promise<{ success: boolean; error?: string }> {
  try {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: request.reason || 'Approve Thronos wallet operation',
      cancelLabel: 'Cancel',
      fallbackLabel: 'Use Device Passcode',
      disableDeviceFallback: request.allowDevicePasscode !== true,
    });
    // Explicit cancel/denial/lockout returns once. The application never
    // retries with a separate PIN or a weaker authentication mechanism.
    return result.success
      ? { success: true }
      : { success: false, error: result.error || 'device_authentication_failed' };
  } catch (_error) {
    return { success: false, error: 'device_authentication_unavailable' };
  }
}

export const MOBILE_SDK_PLATFORM_ADAPTERS = {
  secureKeyProvider: getOrCreateMobileSdkStorageKey,
  deviceAuthenticator: approveMobileSdkOperation,
};
