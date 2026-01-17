# THRONOS COMPLETE NATIVE ECOSYSTEM
## iOS + Android + Browser + CarPlay + Android Auto

**Date**: 2026-01-17
**Status**: Production Ready Specifications
**Based on**: Existing wallet widget philosophy + Mobile SDK

---

## 🎯 OVERVIEW

Complete native implementation across all platforms:

1. **iOS Native App** (Swift + CarPlay)
2. **Android Native App** (Kotlin + Android Auto)
3. **Browser Extension** (Chromium/Firefox)
4. **CarPlay Integration** (On-the-go wallet)
5. **Android Auto Integration** (Voice commands + safety)

All maintaining the **crosschain philosophy** from the base wallet widget!

---

## 📱 PART 1: iOS NATIVE WALLET + CARPLAY

### Project Structure

```
ThronosWallet-iOS/
├── ThronosWallet/
│   ├── App/
│   │   ├── ThronosWalletApp.swift       # SwiftUI App entry
│   │   ├── AppDelegate.swift             # App lifecycle
│   │   └── CarPlaySceneDelegate.swift    # CarPlay integration
│   ├── Views/
│   │   ├── WalletHomeView.swift          # Main wallet screen
│   │   ├── SendView.swift                # Send tokens
│   │   ├── ReceiveView.swift             # QR code receive
│   │   ├── SwapView.swift                # Cross-swap
│   │   ├── PoolsView.swift               # Liquidity pools
│   │   ├── T2EView.swift                 # T2E dashboard
│   │   ├── HistoryView.swift             # Transaction history
│   │   ├── SettingsView.swift            # App settings
│   │   └── CarPlay/
│   │       ├── CarPlayTemplates.swift    # CarPlay UI templates
│   │       └── CarPlayCommands.swift     # Voice commands
│   ├── Services/
│   │   ├── WalletService.swift           # HD wallet ops
│   │   ├── APIService.swift              # Backend API
│   │   ├── KeychainService.swift         # Secure storage
│   │   ├── BiometricService.swift        # Face ID/Touch ID
│   │   ├── NotificationService.swift     # Push notifications
│   │   └── GPSService.swift              # Location services
│   ├── Models/
│   │   ├── Wallet.swift                  # Wallet model
│   │   ├── Token.swift                   # Token model
│   │   ├── Transaction.swift             # TX model
│   │   ├── Pool.swift                    # Pool model
│   │   └── T2EData.swift                 # T2E stats
│   └── Utilities/
│       ├── BIP39.swift                   # Mnemonic generation
│       ├── BIP32.swift                   # HD key derivation
│       ├── Crypto.swift                  # SHA256, encryption
│       └── Extensions.swift              # Helper extensions
├── ThronosWalletIntents/                 # Siri Shortcuts
├── ThronosWalletWidget/                  # Home Screen widget
└── Info.plist
```

### Key Features

#### 1. HD Wallet (BIP39/BIP44)

```swift
import CryptoKit
import CommonCrypto

class WalletService {
    static let shared = WalletService()

    // Create new wallet
    func createWallet(password: String) -> (mnemonic: String, address: String)? {
        // Generate 12-word mnemonic
        guard let mnemonic = BIP39.generate(strength: 128) else { return nil }

        // Convert to seed
        let seed = BIP39.mnemonicToSeed(mnemonic: mnemonic, passphrase: "")

        // Derive Thronos address (m/44'/9001'/0'/0/0)
        let masterKey = BIP32.createMasterKey(seed: seed)
        let derivedKey = BIP32.derivePath(
            masterKey: masterKey,
            path: "m/44'/9001'/0'/0/0"
        )

        // Generate address
        let publicKey = derivedKey.publicKey
        let address = "THR" + publicKey.prefix(33).hexString

        // Encrypt and save
        saveToKeychain(mnemonic: mnemonic, password: password)
        saveAddress(address)

        return (mnemonic, address)
    }

    // Restore from mnemonic
    func restoreWallet(mnemonic: String, password: String) -> String? {
        guard BIP39.validate(mnemonic: mnemonic) else { return nil }

        let seed = BIP39.mnemonicToSeed(mnemonic: mnemonic, passphrase: "")
        let masterKey = BIP32.createMasterKey(seed: seed)
        let derivedKey = BIP32.derivePath(
            masterKey: masterKey,
            path: "m/44'/9001'/0'/0/0"
        )

        let address = "THR" + derivedKey.publicKey.prefix(33).hexString

        saveToKeychain(mnemonic: mnemonic, password: password)
        saveAddress(address)

        return address
    }

    // Keychain storage
    private func saveToKeychain(mnemonic: String, password: String) {
        let encrypted = encrypt(mnemonic, password: password)

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: "thronos_mnemonic",
            kSecValueData as String: encrypted
        ]

        SecItemDelete(query as CFDictionary)
        SecItemAdd(query as CFDictionary, nil)
    }

    private func encrypt(_ data: String, password: String) -> Data {
        // AES-256 encryption
        let key = SHA256.hash(data: password.data(using: .utf8)!)
        // ... encryption logic
        return Data() // Placeholder
    }
}
```

#### 2. Biometric Authentication

```swift
import LocalAuthentication

class BiometricService {
    static let shared = BiometricService()

    func authenticate(reason: String, completion: @escaping (Bool) -> Void) {
        let context = LAContext()
        var error: NSError?

        // Check if biometrics available
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {
            completion(false)
            return
        }

        // Authenticate
        context.evaluatePolicy(
            .deviceOwnerAuthenticationWithBiometrics,
            localizedReason: reason
        ) { success, error in
            DispatchQueue.main.async {
                completion(success)
            }
        }
    }

    func getBiometricType() -> String {
        let context = LAContext()

        if context.biometryType == .faceID {
            return "Face ID"
        } else if context.biometryType == .touchID {
            return "Touch ID"
        } else {
            return "Passcode"
        }
    }
}
```

#### 3. CarPlay Integration

```swift
// CarPlaySceneDelegate.swift
import CarPlay

class CarPlaySceneDelegate: UIResponder, CPTemplateApplicationSceneDelegate {

    var interfaceController: CPInterfaceController?

    func templateApplicationScene(
        _ templateApplicationScene: CPTemplateApplicationScene,
        didConnect interfaceController: CPInterfaceController
    ) {
        self.interfaceController = interfaceController

        // Create main menu
        let mainTemplate = createMainTemplate()
        interfaceController.setRootTemplate(mainTemplate, animated: true)
    }

    // Main CarPlay Menu
    func createMainTemplate() -> CPListTemplate {
        let balanceItem = CPListItem(
            text: "View Balance",
            detailText: "Check your THR balance"
        )
        balanceItem.handler = { [weak self] item, completion in
            self?.showBalance()
            completion()
        }

        let sendItem = CPListItem(
            text: "Quick Send",
            detailText: "Send THR to saved contact"
        )
        sendItem.handler = { [weak self] item, completion in
            self?.showQuickSend()
            completion()
        }

        let historyItem = CPListItem(
            text: "Recent Transactions",
            detailText: "View transaction history"
        )
        historyItem.handler = { [weak self] item, completion in
            self?.showHistory()
            completion()
        }

        let parkingItem = CPListItem(
            text: "Smart Parking",
            detailText: "Find & reserve parking spot"
        )
        parkingItem.handler = { [weak self] item, completion in
            self?.showParking()
            completion()
        }

        let section = CPListSection(items: [
            balanceItem,
            sendItem,
            historyItem,
            parkingItem
        ])

        let template = CPListTemplate(
            title: "Thronos Wallet",
            sections: [section]
        )

        return template
    }

    // Show balance
    func showBalance() {
        APIService.shared.getBalance { result in
            switch result {
            case .success(let balance):
                let template = CPInformationTemplate(
                    title: "Your Balance",
                    layout: .leading,
                    items: [
                        CPInformationItem(title: "THR", detail: "\(balance.thr)"),
                        CPInformationItem(title: "T2E", detail: "\(balance.t2e)"),
                        CPInformationItem(title: "WBTC", detail: "\(balance.wbtc)")
                    ],
                    actions: [
                        CPTextButton(title: "Close") { [weak self] button in
                            self?.interfaceController?.popTemplate(animated: true)
                        }
                    ]
                )

                self.interfaceController?.pushTemplate(template, animated: true)

            case .failure(let error):
                print("Balance error: \(error)")
            }
        }
    }

    // Quick send to saved contacts
    func showQuickSend() {
        // Voice input for amount
        // Select from saved contacts
        // Confirm with biometric
    }

    // Smart parking from CarPlay
    func showParking() {
        // Show nearby parking spots
        // Reserve with THR
        // Navigate to spot
    }
}
```

#### 4. Siri Shortcuts Integration

```swift
// Intent handlers for Siri
import Intents

class CheckBalanceIntentHandler: NSObject, CheckBalanceIntentHandling {
    func handle(intent: CheckBalanceIntent, completion: @escaping (CheckBalanceIntentResponse) -> Void) {
        APIService.shared.getBalance { result in
            switch result {
            case .success(let balance):
                let response = CheckBalanceIntentResponse(code: .success, userActivity: nil)
                response.balance = "\(balance.thr) THR"
                completion(response)

            case .failure:
                let response = CheckBalanceIntentResponse(code: .failure, userActivity: nil)
                completion(response)
            }
        }
    }
}

// Siri Commands:
// "Hey Siri, check my Thronos balance"
// "Hey Siri, send 10 THR to John"
// "Hey Siri, show my T2E score"
```

---

## 🤖 PART 2: ANDROID NATIVE WALLET + ANDROID AUTO

### Project Structure

```
ThronosWallet-Android/
├── app/
│   ├── src/main/
│   │   ├── java/com/thronos/wallet/
│   │   │   ├── MainActivity.kt
│   │   │   ├── WalletApplication.kt
│   │   │   ├── ui/
│   │   │   │   ├── home/HomeFragment.kt
│   │   │   │   ├── send/SendFragment.kt
│   │   │   │   ├── receive/ReceiveFragment.kt
│   │   │   │   ├── swap/SwapFragment.kt
│   │   │   │   ├── pools/PoolsFragment.kt
│   │   │   │   ├── t2e/T2EFragment.kt
│   │   │   │   └── settings/SettingsFragment.kt
│   │   │   ├── auto/
│   │   │   │   ├── ThronosAutoService.kt
│   │   │   │   ├── AutoScreen.kt
│   │   │   │   └── VoiceCommands.kt
│   │   │   ├── services/
│   │   │   │   ├── WalletService.kt
│   │   │   │   ├── APIService.kt
│   │   │   │   ├── BiometricService.kt
│   │   │   │   ├── NotificationService.kt
│   │   │   │   └── GPSService.kt
│   │   │   ├── data/
│   │   │   │   ├── models/
│   │   │   │   ├── repository/
│   │   │   │   └── database/
│   │   │   └── utils/
│   │   │       ├── BIP39.kt
│   │   │       ├── BIP32.kt
│   │   │       ├── Crypto.kt
│   │   │       └── Extensions.kt
│   │   ├── res/
│   │   │   ├── layout/
│   │   │   ├── values/
│   │   │   └── xml/automotive_app_desc.xml
│   │   └── AndroidManifest.xml
│   └── build.gradle
```

### Key Features

#### 1. HD Wallet Implementation

```kotlin
import javax.crypto.Cipher
import javax.crypto.spec.SecretKeySpec
import android.security.keystore.KeyGenParameterSpec
import androidx.security.crypto.EncryptedSharedPreferences

class WalletService(private val context: Context) {

    companion object {
        private const val PREFS_NAME = "thronos_wallet"
        private const val KEY_MNEMONIC = "mnemonic"
        private const val KEY_ADDRESS = "address"
    }

    private val encryptedPrefs by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        EncryptedSharedPreferences.create(
            context,
            PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    // Create new wallet
    fun createWallet(password: String): Pair<String, String>? {
        // Generate 12-word mnemonic
        val mnemonic = BIP39.generateMnemonic(entropy = 128) ?: return null

        // Convert to seed
        val seed = BIP39.mnemonicToSeed(mnemonic, passphrase = "")

        // Derive Thronos address (m/44'/9001'/0'/0/0)
        val masterKey = BIP32.createMasterKey(seed)
        val derivedKey = BIP32.derivePath(
            masterKey,
            path = "m/44'/9001'/0'/0/0"
        )

        // Generate address
        val publicKey = derivedKey.publicKey
        val address = "THR" + publicKey.take(33).toHexString()

        // Save encrypted
        saveToEncryptedPrefs(mnemonic, address, password)

        return Pair(mnemonic, address)
    }

    // Restore from mnemonic
    fun restoreWallet(mnemonic: String, password: String): String? {
        if (!BIP39.validateMnemonic(mnemonic)) return null

        val seed = BIP39.mnemonicToSeed(mnemonic, passphrase = "")
        val masterKey = BIP32.createMasterKey(seed)
        val derivedKey = BIP32.derivePath(
            masterKey,
            path = "m/44'/9001'/0'/0/0"
        )

        val address = "THR" + derivedKey.publicKey.take(33).toHexString()

        saveToEncryptedPrefs(mnemonic, address, password)

        return address
    }

    private fun saveToEncryptedPrefs(mnemonic: String, address: String, password: String) {
        val encrypted = encrypt(mnemonic, password)

        encryptedPrefs.edit()
            .putString(KEY_MNEMONIC, encrypted)
            .putString(KEY_ADDRESS, address)
            .apply()
    }

    private fun encrypt(data: String, password: String): String {
        val key = sha256(password).take(32).toByteArray()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        val secretKey = SecretKeySpec(key, "AES")

        cipher.init(Cipher.ENCRYPT_MODE, secretKey)
        val encrypted = cipher.doFinal(data.toByteArray())

        return Base64.encodeToString(encrypted, Base64.DEFAULT)
    }
}
```

#### 2. Biometric Authentication

```kotlin
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat

class BiometricService(private val activity: FragmentActivity) {

    fun authenticate(
        title: String,
        subtitle: String,
        onSuccess: () -> Unit,
        onError: (String) -> Unit
    ) {
        val executor = ContextCompat.getMainExecutor(activity)

        val biometricPrompt = BiometricPrompt(
            activity,
            executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    super.onAuthenticationSucceeded(result)
                    onSuccess()
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    super.onAuthenticationError(errorCode, errString)
                    onError(errString.toString())
                }

                override fun onAuthenticationFailed() {
                    super.onAuthenticationFailed()
                    onError("Authentication failed")
                }
            }
        )

        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle(subtitle)
            .setNegativeButtonText("Cancel")
            .build()

        biometricPrompt.authenticate(promptInfo)
    }

    fun checkBiometricAvailability(): BiometricStatus {
        val biometricManager = BiometricManager.from(activity)

        return when (biometricManager.canAuthenticate(BIOMETRIC_STRONG)) {
            BiometricManager.BIOMETRIC_SUCCESS -> BiometricStatus.AVAILABLE
            BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE -> BiometricStatus.NO_HARDWARE
            BiometricManager.BIOMETRIC_ERROR_HW_UNAVAILABLE -> BiometricStatus.UNAVAILABLE
            BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED -> BiometricStatus.NOT_ENROLLED
            else -> BiometricStatus.UNKNOWN
        }
    }

    enum class BiometricStatus {
        AVAILABLE, NO_HARDWARE, UNAVAILABLE, NOT_ENROLLED, UNKNOWN
    }
}
```

#### 3. Android Auto Integration

```kotlin
// ThronosAutoService.kt
import androidx.car.app.CarAppService
import androidx.car.app.Screen
import androidx.car.app.Session
import androidx.car.app.validation.HostValidator

class ThronosAutoService : CarAppService() {

    override fun createHostValidator(): HostValidator {
        return HostValidator.ALLOW_ALL_HOSTS_VALIDATOR
    }

    override fun onCreateSession(): Session {
        return ThronosAutoSession()
    }
}

class ThronosAutoSession : Session() {

    override fun onCreateScreen(intent: Intent): Screen {
        return WalletMainScreen(carContext)
    }
}

// Wallet Main Screen for Android Auto
import androidx.car.app.model.*

class WalletMainScreen(carContext: CarContext) : Screen(carContext) {

    override fun onGetTemplate(): Template {
        return ListTemplate.Builder()
            .setSingleList(createMenuList())
            .setTitle("Thronos Wallet")
            .setHeaderAction(Action.APP_ICON)
            .build()
    }

    private fun createMenuList(): ItemList {
        return ItemList.Builder()
            .addItem(
                Row.Builder()
                    .setTitle("View Balance")
                    .setBrowsable(false)
                    .setOnClickListener { showBalance() }
                    .build()
            )
            .addItem(
                Row.Builder()
                    .setTitle("Quick Send")
                    .setBrowsable(false)
                    .setOnClickListener { showQuickSend() }
                    .build()
            )
            .addItem(
                Row.Builder()
                    .setTitle("Recent Transactions")
                    .setBrowsable(true)
                    .setOnClickListener { showHistory() }
                    .build()
            )
            .addItem(
                Row.Builder()
                    .setTitle("Smart Parking")
                    .setBrowsable(true)
                    .setOnClickListener { showParking() }
                    .build()
            )
            .build()
    }

    private fun showBalance() {
        APIService.getBalance { result ->
            when (result) {
                is Result.Success -> {
                    val template = MessageTemplate.Builder("Your Balance")
                        .setMessage(
                            "THR: ${result.data.thr}\n" +
                            "T2E: ${result.data.t2e}\n" +
                            "WBTC: ${result.data.wbtc}"
                        )
                        .addAction(
                            Action.Builder()
                                .setTitle("Close")
                                .setOnClickListener { screenManager.pop() }
                                .build()
                        )
                        .build()

                    screenManager.push(BalanceScreen(carContext, template))
                }
                is Result.Error -> {
                    // Show error
                }
            }
        }
    }

    private fun showParking() {
        // Show nearby parking spots with GPS
        // Reserve with voice confirmation
        // Navigate to spot with Android Auto navigation
    }
}
```

#### 4. Voice Commands

```kotlin
// VoiceCommands.kt
import android.speech.RecognizerIntent

class VoiceCommandHandler(private val context: Context) {

    fun processVoiceCommand(command: String): VoiceCommandResult {
        return when {
            command.contains("balance", ignoreCase = true) -> {
                VoiceCommandResult.CheckBalance
            }

            command.contains("send", ignoreCase = true) -> {
                val amount = extractAmount(command)
                val recipient = extractRecipient(command)
                VoiceCommandResult.SendTokens(amount, recipient)
            }

            command.contains("t2e", ignoreCase = true) ||
            command.contains("train to earn", ignoreCase = true) -> {
                VoiceCommandResult.CheckT2E
            }

            command.contains("parking", ignoreCase = true) -> {
                VoiceCommandResult.FindParking
            }

            else -> VoiceCommandResult.Unknown
        }
    }

    private fun extractAmount(command: String): Double? {
        val regex = "\\d+(\\.\\d+)?".toRegex()
        val match = regex.find(command)
        return match?.value?.toDoubleOrNull()
    }

    private fun extractRecipient(command: String): String? {
        // Extract "to John" or "to THR..."
        val toRegex = "to\\s+(\\w+)".toRegex(RegexOption.IGNORE_CASE)
        val match = toRegex.find(command)
        return match?.groupValues?.get(1)
    }

    sealed class VoiceCommandResult {
        object CheckBalance : VoiceCommandResult()
        data class SendTokens(val amount: Double?, val recipient: String?) : VoiceCommandResult()
        object CheckT2E : VoiceCommandResult()
        object FindParking : VoiceCommandResult()
        object Unknown : VoiceCommandResult()
    }
}

// Voice Examples:
// "Check my Thronos balance"
// "Send 10 THR to John"
// "Show my T2E score"
// "Find parking near me"
// "Reserve parking spot P-102"
```

---

## 🌐 PART 3: BROWSER EXTENSION (Chromium/Firefox)

### Project Structure

```
thronos-browser-extension/
├── manifest.json                         # Extension manifest (V3)
├── background/
│   ├── service-worker.js                 # Background service
│   ├── wallet-manager.js                 # Wallet operations
│   └── auto-services.js                  # Automatic ecosystem services
├── popup/
│   ├── popup.html                        # Extension popup
│   ├── popup.js                          # Popup logic
│   └── popup.css                         # Styling
├── content/
│   ├── content.js                        # Content script (dApp provider)
│   ├── injected.js                       # window.thronos API
│   └── auto-interactions.js              # Auto-service injections
├── pages/
│   ├── onboarding.html                   # First-time setup
│   ├── settings.html                     # Extension settings
│   └── transaction-confirm.html          # TX confirmation page
├── utils/
│   ├── bip39.js                          # Mnemonic generation
│   ├── bip32.js                          # Key derivation
│   ├── crypto.js                         # Encryption
│   └── api.js                            # Backend communication
└── icons/
    ├── icon-16.png
    ├── icon-48.png
    └── icon-128.png
```

### Manifest V3

```json
{
  "manifest_version": 3,
  "name": "Thronos Wallet",
  "version": "1.0.0",
  "description": "Your gateway to the Thronos ecosystem",

  "permissions": [
    "storage",
    "activeTab",
    "geolocation",
    "notifications",
    "webRequest"
  ],

  "host_permissions": [
    "https://thrchain.up.railway.app/*",
    "https://thrchain.vercel.app/*",
    "http://localhost:5000/*"
  ],

  "background": {
    "service_worker": "background/service-worker.js"
  },

  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": {
      "16": "icons/icon-16.png",
      "48": "icons/icon-48.png",
      "128": "icons/icon-128.png"
    }
  },

  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content/content.js"],
      "run_at": "document_start"
    }
  ],

  "web_accessible_resources": [
    {
      "resources": ["content/injected.js"],
      "matches": ["<all_urls>"]
    }
  ]
}
```

### Auto-Services Feature

```javascript
// background/auto-services.js

class AutoServices {
  constructor() {
    this.services = {
      telemetry: { enabled: true, interval: 60000 },
      t2e: { enabled: true },
      parking: { enabled: true },
      priceAlerts: { enabled: true, threshold: 0.01 }
    };

    this.startServices();
  }

  startServices() {
    // Auto telemetry submission
    if (this.services.telemetry.enabled) {
      setInterval(() => {
        this.submitTelemetry();
      }, this.services.telemetry.interval);
    }

    // Auto T2E contributions
    if (this.services.t2e.enabled) {
      this.watchForT2EOpportunities();
    }

    // Smart parking notifications
    if (this.services.parking.enabled) {
      this.watchParkingNearby();
    }

    // Price alerts
    if (this.services.priceAlerts.enabled) {
      this.monitorPrices();
    }
  }

  async submitTelemetry() {
    try {
      // Get GPS if available
      const position = await this.getCurrentPosition();

      const telemetry = {
        timestamp: new Date().toISOString(),
        gps: {
          lat: position.coords.latitude,
          lon: position.coords.longitude
        },
        browser: {
          userAgent: navigator.userAgent,
          platform: navigator.platform
        }
      };

      // Submit to /api/iot/submit_gps
      await this.apiCall('/api/iot/submit_gps', telemetry);

      console.log('✅ Telemetry submitted automatically');

    } catch (e) {
      console.error('Telemetry submission failed:', e);
    }
  }

  watchForT2EOpportunities() {
    // Listen for helpful AI responses (thumbs up)
    chrome.storage.onChanged.addListener((changes, namespace) => {
      if (changes.lastAIResponse && changes.lastAIResponse.newValue?.helpful) {
        this.submitT2EFeedback(changes.lastAIResponse.newValue);
      }
    });
  }

  async watchParkingNearby() {
    const position = await this.getCurrentPosition();

    // Check for nearby parking spots
    const response = await this.apiCall('/api/iot/parking/nearby', {
      lat: position.coords.latitude,
      lon: position.coords.longitude,
      radius: 1000 // 1km
    });

    if (response.available_spots > 0) {
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon-128.png',
        title: 'Parking Available',
        message: `${response.available_spots} spots nearby. Tap to reserve.`
      });
    }
  }

  async monitorPrices() {
    setInterval(async () => {
      const prices = await this.apiCall('/api/prices');
      const stored = await chrome.storage.local.get('lastPrice');

      if (stored.lastPrice) {
        const change = Math.abs(prices.thr - stored.lastPrice.thr);
        const changePercent = (change / stored.lastPrice.thr) * 100;

        if (changePercent >= this.services.priceAlerts.threshold * 100) {
          chrome.notifications.create({
            type: 'basic',
            iconUrl: 'icons/icon-128.png',
            title: 'Price Alert!',
            message: `THR ${changePercent > 0 ? '+' : ''}${changePercent.toFixed(2)}%`
          });
        }
      }

      await chrome.storage.local.set({ lastPrice: prices });

    }, 60000); // Check every minute
  }

  getCurrentPosition() {
    return new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject);
    });
  }

  async apiCall(endpoint, data = {}) {
    const response = await fetch(`https://thrchain.up.railway.app${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    return response.json();
  }
}

// Initialize auto-services
const autoServices = new AutoServices();
```

### dApp Provider (window.thronos)

```javascript
// content/injected.js

(function() {
  if (window.thronos) return; // Already injected

  class ThronosProvider {
    constructor() {
      this.isThronos = true;
      this.isConnected = false;
      this.selectedAddress = null;
    }

    // Connect wallet
    async connect() {
      const response = await this.sendMessage({
        method: 'eth_requestAccounts'
      });

      if (response.result) {
        this.isConnected = true;
        this.selectedAddress = response.result[0];
        return response.result;
      }

      throw new Error('User rejected connection');
    }

    // Get current address
    async getAddress() {
      if (!this.isConnected) {
        throw new Error('Not connected');
      }

      return this.selectedAddress;
    }

    // Get balance
    async getBalance(token = 'THR') {
      const response = await this.sendMessage({
        method: 'wallet_getBalance',
        params: { token }
      });

      return response.result;
    }

    // Send transaction
    async sendTransaction(to, amount, token = 'THR') {
      const response = await this.sendMessage({
        method: 'wallet_sendTransaction',
        params: { to, amount, token }
      });

      return response.result;
    }

    // Sign message
    async signMessage(message) {
      const response = await this.sendMessage({
        method: 'personal_sign',
        params: [message, this.selectedAddress]
      });

      return response.result;
    }

    // Internal: Send message to extension
    sendMessage(payload) {
      return new Promise((resolve, reject) => {
        window.postMessage({
          target: 'thronos-extension',
          data: payload
        }, '*');

        window.addEventListener('message', function handler(event) {
          if (event.data.target === 'thronos-page' && event.data.id === payload.id) {
            window.removeEventListener('message', handler);

            if (event.data.error) {
              reject(new Error(event.data.error));
            } else {
              resolve(event.data);
            }
          }
        });
      });
    }
  }

  // Inject provider
  window.thronos = new ThronosProvider();

  // Announce provider
  window.dispatchEvent(new Event('thronos#initialized'));

  console.log('🟢 Thronos Wallet provider injected');
})();
```

---

## ✅ COMPLETE IMPLEMENTATION CHECKLIST

### iOS (Swift + CarPlay)
- [ ] HD wallet generation
- [ ] Keychain secure storage
- [ ] Face ID/Touch ID auth
- [ ] Multi-token support
- [ ] Cross-swap implementation
- [ ] T2E dashboard
- [ ] CarPlay templates
- [ ] Siri shortcuts
- [ ] Push notifications
- [ ] GPS telemetry

### Android (Kotlin + Android Auto)
- [ ] HD wallet generation
- [ ] EncryptedSharedPreferences
- [ ] Fingerprint/Face auth
- [ ] Multi-token support
- [ ] Cross-swap implementation
- [ ] T2E dashboard
- [ ] Android Auto screens
- [ ] Voice commands
- [ ] Push notifications
- [ ] GPS telemetry

### Browser Extension
- [ ] Manifest V3 setup
- [ ] HD wallet in extension
- [ ] Secure storage (chrome.storage)
- [ ] dApp provider (window.thronos)
- [ ] Auto-services (telemetry, T2E, parking, alerts)
- [ ] Transaction confirmation UI
- [ ] Multi-tab sync

---

## 🚀 DEPLOYMENT TIMELINE

**Week 1-2**: iOS core wallet
**Week 3-4**: Android core wallet
**Week 5-6**: Browser extension
**Week 7**: CarPlay + Android Auto integration
**Week 8**: Testing & launch

**Beta testers needed**: 100 users
**App Store review**: 2-3 weeks
**Play Store review**: 1-2 weeks

---

## 🎯 SUCCESS METRICS

- 1,000+ app downloads in 3 months
- 500+ daily active users
- 10,000+ transactions/month
- 100+ T2E contributors/week
- 50+ CarPlay/Auto users

**Let's build the complete Thronos native ecosystem!** 🚀
