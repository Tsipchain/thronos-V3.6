# Thronos Network - Mobile SDK

*Pledge to the unburnable • Strength in every link, light in every Block*

The official mobile SDK for Thronos Network, supporting React Native, iOS (Swift), and Android (Kotlin).

## Features

- **Wallet Management**: Create, import, and manage Thronos wallets
- **Token Operations**: View balances, send transactions
- **Secure Storage**: Encrypted wallet storage using platform-specific secure storage
- **Cross-Platform**: Works on React Native, iOS, and Android
- **TypeScript Support**: Full TypeScript definitions included
- **Comprehensive API**: Access all Thronos Network features

## Installation

### React Native

```bash
npm install thronos-mobile-sdk
# or
yarn add thronos-mobile-sdk
```

Also install peer dependencies:

```bash
npm install @react-native-async-storage/async-storage react-native-crypto-js
```

### iOS (Swift)

1. Copy `ios/ThronosSDK.swift` to your Xcode project
2. Ensure you have enabled Keychain access in your project capabilities

### Android (Kotlin)

1. Copy `android/ThronosSDK.kt` to your Android project
2. Add dependencies to your `build.gradle`:

```gradle
dependencies {
    implementation 'com.google.code.gson:gson:2.10'
    implementation 'com.squareup.okhttp3:okhttp:4.11.0'
    implementation 'androidx.security:security-crypto:1.1.0-alpha06'
    implementation 'org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.1'
}
```

## Quick Start

### React Native

```javascript
import ThronosSDK from 'thronos-mobile-sdk';

// Initialize SDK
const thronos = new ThronosSDK({
    apiUrl: 'http://localhost:5000',
    network: 'mainnet',
    autoSave: true
});

// Create a new wallet
const wallet = await thronos.createWallet();
console.log('Wallet created:', wallet.address);

// Or import existing wallet
await thronos.importWallet('THR...', 'secret_key');

// Get balances
const balances = await thronos.getBalances();
console.log('Tokens:', balances.tokens);

// Send transaction
await thronos.sendTransaction('THR...recipient', 100, 'THR');
```

### iOS (Swift)

```swift
import Foundation

// Initialize SDK
let thronos = ThronosSDK(apiUrl: "http://localhost:5000", network: "mainnet")

// Create a new wallet
thronos.createWallet { result in
    switch result {
    case .success(let wallet):
        print("Wallet created: \(wallet.address)")
    case .failure(let error):
        print("Error: \(error.localizedDescription)")
    }
}

// Get balances
thronos.getBalances { result in
    switch result {
    case .success(let response):
        print("Tokens: \(response.tokens)")
    case .failure(let error):
        print("Error: \(error.localizedDescription)")
    }
}

// Send transaction
thronos.sendTransaction(to: "THR...recipient", amount: 100.0, token: "THR") { result in
    switch result {
    case .success(let response):
        print("Transaction sent: \(response.transaction?.hash ?? "")")
    case .failure(let error):
        print("Error: \(error.localizedDescription)")
    }
}
```

### Android (Kotlin)

```kotlin
import com.thronos.sdk.ThronosSDK
import kotlinx.coroutines.launch
import kotlinx.coroutines.GlobalScope

// Initialize SDK
val thronos = ThronosSDK(context, apiUrl = "http://localhost:5000")

// Create a new wallet
GlobalScope.launch {
    val result = thronos.createWallet()
    result.onSuccess { wallet ->
        println("Wallet created: ${wallet.address}")
    }.onFailure { error ->
        println("Error: ${error.message}")
    }
}

// Get balances
GlobalScope.launch {
    val result = thronos.getBalances()
    result.onSuccess { response ->
        println("Tokens: ${response.tokens}")
    }.onFailure { error ->
        println("Error: ${error.message}")
    }
}

// Send transaction
GlobalScope.launch {
    val result = thronos.sendTransaction("THR...recipient", 100.0, "THR")
    result.onSuccess { response ->
        println("Transaction sent: ${response.transaction?.hash}")
    }.onFailure { error ->
        println("Error: ${error.message}")
    }
}
```

## API Reference

### Wallet Management

#### `createWallet()`
Creates a new Thronos wallet.

**Returns:** `Promise<{address: string, secret: string}>`

**Example:**
```javascript
const wallet = await thronos.createWallet();
console.log('Address:', wallet.address);
console.log('Secret:', wallet.secret);
```

#### `importWallet(address, secret)`
Imports an existing wallet.

**Parameters:**
- `address` (string): Wallet address starting with "THR"
- `secret` (string): Wallet secret key

**Returns:** `Promise<{address: string, secret: string}>`

**Example:**
```javascript
await thronos.importWallet('THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a', 'your_secret_key');
```

#### `getWallet()`
Gets the currently connected wallet.

**Returns:** `Promise<{address: string, secret: string}|null>`

#### `isConnected()`
Checks if a wallet is connected.

**Returns:** `Promise<boolean>`

#### `disconnect()`
Disconnects the current wallet and removes it from storage.

**Returns:** `Promise<void>`

### Token Operations

#### `getBalances(address?, showZero?)`
Gets token balances for a wallet.

**Parameters:**
- `address` (string, optional): Wallet address (uses current wallet if not provided)
- `showZero` (boolean, optional): Show tokens with zero balance (default: false)

**Returns:** `Promise<{address: string, tokens: Array, last_updated: string}>`

**Example:**
```javascript
const balances = await thronos.getBalances();
balances.tokens.forEach(token => {
    console.log(`${token.symbol}: ${token.balance}`);
});
```

#### `getTokenBalance(tokenSymbol, address?)`
Gets balance for a specific token.

**Parameters:**
- `tokenSymbol` (string): Token symbol (e.g., 'THR', 'WBTC')
- `address` (string, optional): Wallet address

**Returns:** `Promise<number>`

**Example:**
```javascript
const thrBalance = await thronos.getTokenBalance('THR');
console.log('THR Balance:', thrBalance);
```

#### `sendTransaction(to, amount, token?)`
Sends a transaction.

**Parameters:**
- `to` (string): Recipient address
- `amount` (number): Amount to send
- `token` (string, optional): Token symbol (default: 'THR')

**Returns:** `Promise<{success: boolean, transaction: object}>`

**Example:**
```javascript
const result = await thronos.sendTransaction(
    'THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a',
    100,
    'THR'
);
console.log('Transaction hash:', result.transaction.hash);
```

#### `getTransactionHistory(address?, limit?)`
Gets transaction history for a wallet.

**Parameters:**
- `address` (string, optional): Wallet address
- `limit` (number, optional): Number of transactions (default: 50)

**Returns:** `Promise<Array<Transaction>>`

### Cryptography

#### `signMessage(message)`
Signs a message with the current wallet's secret key.

**Parameters:**
- `message` (string): Message to sign

**Returns:** `Promise<string>`

#### `verifySignature(message, signature, address)`
Verifies a message signature.

**Parameters:**
- `message` (string): Original message
- `signature` (string): Signature to verify
- `address` (string): Address that signed the message

**Returns:** `Promise<boolean>`

### Music & Telemetry (NEW)

#### `getMusicTracks(filters?)`
Gets music tracks from Thronos Music platform.

**Parameters:**
- `filters` (object, optional): Filters like {genre: 'electronic', artist: 'THR...'}

**Returns:** `Promise<{tracks: Array}>`

**Example:**
```javascript
const tracks = await thronos.getMusicTracks({ genre: 'electronic' });
tracks.forEach(track => {
    console.log(`${track.title} by ${track.artist}`);
});
```

#### `sendMusicTip(artistAddress, amount, trackId)`
Send THR tip to music artist.

**Parameters:**
- `artistAddress` (string): Artist's THR address
- `amount` (number): Tip amount in THR
- `trackId` (string): Track ID

**Returns:** `Promise<{success: boolean, transaction: object}>`

**Example:**
```javascript
const result = await thronos.sendMusicTip('THR...artist', 10, 'track-123');
console.log('Tip sent:', result.transaction.hash);
```

#### `recordMusicTelemetry(telemetryData)`
Record music streaming telemetry (plays, duration, location).

**Parameters:**
- `telemetryData` (object): {track_id, duration, lat, lng, device_id}

**Returns:** `Promise<{success: boolean}>`

#### `generateWhisperNote(txData, frequency?)`
Generate audio signal from transaction data (WhisperNote technology).

**Parameters:**
- `txData` (object): Transaction data to encode
- `frequency` (number, optional): Audio frequency 1000-4000 Hz (default: 2000)

**Returns:** `Promise<{success: boolean, audio_url: string}>`

**Example:**
```javascript
const audio = await thronos.generateWhisperNote({
    tx_id: 'TX123',
    amount: 100,
    to: 'THR...'
}, 2000);
console.log('Audio generated:', audio.audio_url);
```

#### `sendGPSTelemetry(location)`
Send GPS telemetry data (vehicle tracking, IoT).

**Parameters:**
- `location` (object): {lat, lng, speed, heading}

**Returns:** `Promise<{success: boolean}>`

**Example:**
```javascript
// Get device location and send telemetry
navigator.geolocation.getCurrentPosition(async (position) => {
    await thronos.sendGPSTelemetry({
        lat: position.coords.latitude,
        lng: position.coords.longitude,
        speed: position.coords.speed || 0,
        heading: position.coords.heading || 0
    });
});
```

#### `getTransactionsByCategory(address?, category?, limit?)`
Get transactions filtered by category.

**Parameters:**
- `address` (string, optional): Wallet address
- `category` (string, optional): Category (mining, liquidity, gateway, music, etc.)
- `limit` (number, optional): Max transactions (default: 50)

**Returns:** `Promise<{transactions: Array}>`

**Categories:**
- `all` - All transactions
- `thr` - THR transfers
- `mining` - Mining rewards
- `tokens` - Token transfers
- `l2e` - Learn-to-Earn
- `ai_credits` - AI Credits
- `iot` - IoT transactions
- `bridge` - Cross-chain bridge
- `swaps` - Token swaps
- `liquidity` - Liquidity pools
- `gateway` - Gateway transactions
- `music` - Music tips/purchases

**Example:**
```javascript
// Get all music-related transactions
const musicTxs = await thronos.getTransactionsByCategory(
    'THR...',
    'music',
    20
);
musicTxs.forEach(tx => {
    console.log(`Music tip: ${tx.amount} THR to ${tx.to}`);
});
```

## Advanced Usage

### Custom API Configuration

```javascript
const thronos = new ThronosSDK({
    apiUrl: 'https://api.thronos.network',
    network: 'mainnet',
    autoSave: true
});
```

### Error Handling

```javascript
try {
    const wallet = await thronos.createWallet();
    console.log('Success:', wallet);
} catch (error) {
    console.error('Error:', error.message);
}
```

### React Native Example App

```javascript
import React, { useEffect, useState } from 'react';
import { View, Text, Button } from 'react-native';
import ThronosSDK from 'thronos-mobile-sdk';

const thronos = new ThronosSDK();

export default function App() {
    const [wallet, setWallet] = useState(null);
    const [balances, setBalances] = useState([]);

    useEffect(() => {
        loadWallet();
    }, []);

    const loadWallet = async () => {
        const w = await thronos.getWallet();
        setWallet(w);
        if (w) {
            const b = await thronos.getBalances();
            setBalances(b.tokens);
        }
    };

    const createWallet = async () => {
        const w = await thronos.createWallet();
        setWallet(w);
        loadWallet();
    };

    return (
        <View style={{ padding: 20 }}>
            {!wallet ? (
                <Button title="Create Wallet" onPress={createWallet} />
            ) : (
                <View>
                    <Text>Address: {wallet.address}</Text>
                    <Text>Balances:</Text>
                    {balances.map(token => (
                        <Text key={token.symbol}>
                            {token.symbol}: {token.balance}
                        </Text>
                    ))}
                </View>
            )}
        </View>
    );
}
```

## Security Best Practices

1. **Never hardcode secret keys**: Always store them securely using the SDK's built-in storage
2. **Use HTTPS**: In production, always use HTTPS for API communication
3. **Validate addresses**: Always validate recipient addresses before sending transactions
4. **Backup wallets**: Implement backup functionality for users to save their secret keys
5. **Test transactions**: Test with small amounts first before sending large transactions

## Platform-Specific Notes

### React Native
- Requires `@react-native-async-storage/async-storage` for secure storage
- Ensure you've linked the native modules

### iOS
- Uses iOS Keychain for secure storage
- Enable Keychain Sharing in Xcode capabilities if needed
- Minimum iOS version: 13.0

### Android
- Uses EncryptedSharedPreferences for secure storage
- Requires AndroidX Security library
- Minimum SDK version: 23 (Android 6.0)

## Troubleshooting

### "Network request failed"
- Ensure the API URL is correct
- Check that your device/emulator can reach the API server
- On Android, ensure you've added INTERNET permission

### "Wallet not saved"
- Check storage permissions
- Ensure AsyncStorage is properly installed (React Native)
- Check that encryption dependencies are installed

### Build errors
- Make sure all peer dependencies are installed
- Clear cache: `npm start -- --reset-cache`
- Clean build folders

## Support

- Documentation: https://thronos.network/docs
- GitHub Issues: https://github.com/Tsipchain/thronos-V3.6/issues
- API Reference: https://thronos.network/api

## License

MIT License - See repository root for details

## Version History

- **1.0.0** - Initial release
  - Wallet creation and import
  - Token balance queries
  - Transaction sending
  - Secure storage for all platforms
  - TypeScript support
