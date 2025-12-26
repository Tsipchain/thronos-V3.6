# Thronos Wallet Chrome Extension

A Chrome browser extension for managing your Thronos Network wallet and interacting with dApps.

## Features

- **Wallet Management**: Create new wallets or import existing ones
- **Token Support**: View balances for THR, WBTC, L2E, and other tokens
- **Send Transactions**: Send tokens to any Thronos address
- **dApp Integration**: Interact with Thronos-enabled websites
- **Secure Storage**: Wallet credentials stored locally in encrypted Chrome storage
- **Auto-refresh**: Automatically update balances every 30 seconds

## Installation

### Development Mode

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" using the toggle in the top right
3. Click "Load unpacked"
4. Select the `chrome-extension` folder from this repository
5. The Thronos Wallet extension should now appear in your extensions list

### Production Mode

Once published to the Chrome Web Store:
1. Visit the Chrome Web Store
2. Search for "Thronos Wallet"
3. Click "Add to Chrome"

## Usage

### Creating a New Wallet

1. Click the Thronos extension icon in your browser toolbar
2. Click "Create New Wallet"
3. **IMPORTANT**: Save your secret key securely - you cannot recover it later!
4. Click "I've Saved It" to confirm

### Importing an Existing Wallet

1. Click the Thronos extension icon
2. Click "Import Wallet"
3. Enter your wallet address (starting with "THR")
4. Enter your secret key
5. Click "Import"

### Viewing Balances

1. Open the extension popup
2. Your total portfolio value is displayed at the top
3. Click the "Tokens" tab to see individual token balances

### Sending Tokens

1. Open the extension popup
2. Click the "Send" tab
3. Select the token you want to send
4. Enter the recipient's address
5. Enter the amount
6. Click "Send"

### Using with dApps

The extension automatically injects the `window.thronos` provider into web pages, allowing dApps to interact with your wallet:

```javascript
// Connect wallet
await window.thronos.connect();

// Get address
const address = await window.thronos.getAddress();

// Get balance
const balance = await window.thronos.getBalance('THR');

// Send transaction
await window.thronos.sendTransaction('THR...', 100, 'THR');
```

## API Configuration

By default, the extension connects to `http://localhost:5000`. To change this:

1. Edit `popup.js` and `content.js`
2. Change the `API_BASE` constant to your production URL
3. Reload the extension

## Security

- Private keys are stored locally using Chrome's encrypted storage
- Private keys never leave your browser
- Always verify transaction details before confirming
- Never share your secret key with anyone

## Troubleshooting

### Extension not loading

- Make sure you've enabled Developer mode in Chrome
- Check the Chrome console for errors
- Try reloading the extension

### Cannot connect to API

- Verify the API is running on `http://localhost:5000`
- Check CORS settings on the API server
- Update the `API_BASE` URL if using a different server

### Transactions failing

- Ensure you have sufficient balance
- Verify the recipient address is valid
- Check the API server logs for errors

## Development

### File Structure

```
chrome-extension/
├── manifest.json       # Extension configuration
├── popup.html         # Extension popup UI
├── popup.js           # Popup logic
├── background.js      # Background service worker
├── content.js         # Content script for dApp integration
├── styles.css         # Popup styles
└── icons/            # Extension icons
```

### Building

No build process required - the extension runs directly from source files.

### Testing

1. Load the extension in development mode
2. Open the Chrome DevTools console
3. Click "Inspect" on the extension popup to debug popup.js
4. Use `chrome://extensions/` to view background script logs

## License

MIT License - See repository root for details

## Support

For issues and questions:
- GitHub Issues: https://github.com/Tsipchain/thronos-V3.6/issues
- Documentation: https://thronos.network/docs

## Version History

- **1.0.0** - Initial release
  - Create/import wallets
  - View token balances
  - Send transactions
  - dApp provider integration
