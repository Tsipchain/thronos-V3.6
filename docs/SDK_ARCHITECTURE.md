# Thronos SDK & Extensions Architecture

## Επισκόπηση / Overview

Αυτό το έγγραφο περιγράφει τη δομή των Thronos SDKs και Extensions για mobile (Android/iOS), web, και automotive platforms (CarPlay/Android Auto).

This document describes the architecture of Thronos SDKs and Extensions for mobile (Android/iOS), web, and automotive platforms (CarPlay/Android Auto).

---

## 1. Core SDK Modules

### 1.1 Wallet SDK
**Τοποθεσία / Location**: `/static/wallet_sdk.js`

**Λειτουργίες / Features**:
- Wallet connection & session management
- Transaction signing & broadcasting
- Balance & transaction history
- Multi-token support (THR, custom tokens)
- NFT integration
- L2E (Learn-to-Earn) rewards

**Mobile Integration**:
```javascript
// Android (Kotlin/Java)
import com.thronos.wallet.WalletSDK

val wallet = WalletSDK.getInstance(context)
wallet.connect(address, authSecret)

// iOS (Swift)
import ThronosWallet

let wallet = ThronosWallet.shared
wallet.connect(address: address, authSecret: authSecret)
```

**Web Integration**:
```javascript
// Browser
import { WalletSDK } from './wallet_sdk.js';

const wallet = new WalletSDK();
await wallet.connect(address, authSecret);
```

---

### 1.2 Music Module SDK
**Τοποθεσία / Location**: `/static/music_module.js`

**Λειτουργίες / Features**:
- Track playback & streaming
- Playlist management (create, add, remove, reorder)
- Offline support with tipping
- Artist earnings tracking
- Play count & tips analytics
- Background playback with MediaSession API

**MediaSession API Support** (CarPlay/Android Auto):
```javascript
// Automatic integration in GlobalMusicPlayer
navigator.mediaSession.metadata = new MediaMetadata({
    title: track.title,
    artist: track.artist_name,
    album: track.album,
    artwork: [{ src: coverUrl, sizes: '512x512' }]
});

// Action handlers
navigator.mediaSession.setActionHandler('play', () => audio.play());
navigator.mediaSession.setActionHandler('pause', () => audio.pause());
navigator.mediaSession.setActionHandler('nexttrack', () => player.next());
navigator.mediaSession.setActionHandler('previoustrack', () => player.previous());
```

**Mobile Integration**:
```kotlin
// Android - MediaSession
val mediaSession = MediaSessionCompat(context, "ThronosMusic")
mediaSession.setMetadata(
    MediaMetadataCompat.Builder()
        .putString(MediaMetadataCompat.METADATA_KEY_TITLE, track.title)
        .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, track.artist)
        .putBitmap(MediaMetadataCompat.METADATA_KEY_ALBUM_ART, coverBitmap)
        .build()
)
```

```swift
// iOS - MPNowPlayingInfoCenter
var nowPlayingInfo = [String: Any]()
nowPlayingInfo[MPMediaItemPropertyTitle] = track.title
nowPlayingInfo[MPMediaItemPropertyArtist] = track.artist
nowPlayingInfo[MPMediaItemPropertyArtwork] = MPMediaItemArtwork(image: coverImage)
MPNowPlayingInfoCenter.default().nowPlayingInfo = nowPlayingInfo
```

---

### 1.3 Authentication SDK
**Τοποθεσία / Location**: `/static/wallet_auth.js`

**Λειτουργίες / Features**:
- PIN-based wallet unlock
- Session management (sessionStorage)
- Auth secret caching
- Biometric authentication (mobile)

**Mobile Biometric Integration**:
```kotlin
// Android - BiometricPrompt
val biometricPrompt = BiometricPrompt(activity, executor,
    object : BiometricPrompt.AuthenticationCallback() {
        override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
            // Unlock wallet with cached secret
            wallet.unlock(cachedAuthSecret)
        }
    })
```

```swift
// iOS - LocalAuthentication
import LocalAuthentication

let context = LAContext()
context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics,
                      localizedReason: "Unlock Thronos Wallet") { success, error in
    if success {
        // Unlock wallet
        wallet.unlock(with: cachedAuthSecret)
    }
}
```

---

## 2. Extension Architecture

### 2.1 GPS Telemetry Extension
**Purpose**: Collect GPS data for autopilot training & route optimization

**Data Structure**:
```json
{
  "session_id": "SESSION-{timestamp}-{hash}",
  "wallet_address": "THR...",
  "telemetry": [
    {
      "timestamp": "2026-01-10T12:00:00Z",
      "latitude": 37.9838,
      "longitude": 23.7275,
      "speed": 50.5,
      "heading": 180.0,
      "altitude": 100.5,
      "accuracy": 5.0,
      "music_playing": true,
      "track_id": "TRACK-123...",
      "driving_mode": "highway"
    }
  ],
  "routes": [
    {
      "route_id": "ROUTE-{hash}",
      "start": { "lat": 37.9838, "lon": 23.7275 },
      "end": { "lat": 38.0000, "lon": 23.8000 },
      "waypoints": [...],
      "preferences": {
        "avoid_tolls": false,
        "prefer_highways": true,
        "music_genres": ["rock", "electronic"]
      }
    }
  ]
}
```

**Mobile Integration**:
```kotlin
// Android - Location Services
val locationManager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
locationManager.requestLocationUpdates(
    LocationManager.GPS_PROVIDER,
    1000L, // 1 second
    10f,   // 10 meters
    object : LocationListener {
        override fun onLocationChanged(location: Location) {
            telemetry.record(
                latitude = location.latitude,
                longitude = location.longitude,
                speed = location.speed,
                heading = location.bearing
            )
        }
    }
)
```

```swift
// iOS - CoreLocation
import CoreLocation

class TelemetryManager: NSObject, CLLocationManagerDelegate {
    let locationManager = CLLocationManager()

    func startTracking() {
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyBest
        locationManager.startUpdatingLocation()
    }

    func locationManager(_ manager: CLLocationManager,
                        didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }

        telemetry.record(
            latitude: location.coordinate.latitude,
            longitude: location.coordinate.longitude,
            speed: location.speed,
            heading: location.course
        )
    }
}
```

---

### 2.2 Autopilot Training Extension

**Purpose**: Machine learning για αυτόματη οδήγηση βασισμένη σε GPS routes & προτιμήσεις χρηστών

**Training Data Collection**:
```python
# Server-side ML training
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_autopilot_model(telemetry_data):
    """
    Train autopilot model από GPS telemetry

    Features:
    - Current location (lat, lon)
    - Current speed & heading
    - Historical routes
    - User preferences (avoid tolls, prefer highways)
    - Music preferences (correlate with driving style)

    Targets:
    - Optimal speed
    - Optimal heading
    - Lane preference
    - Route selection
    """
    X = np.array([
        [entry['latitude'], entry['longitude'], entry['speed'], entry['heading']]
        for entry in telemetry_data
    ])

    y = np.array([
        entry['optimal_heading']  # Target variable
        for entry in telemetry_data
    ])

    model = RandomForestRegressor(n_estimators=100)
    model.fit(X, y)

    return model
```

**Route Recommendation**:
```javascript
// Client-side route recommendation
async function getOptimalRoute(start, end, preferences) {
    const response = await fetch('/api/autopilot/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            start: { lat: start.latitude, lon: start.longitude },
            end: { lat: end.latitude, lon: end.longitude },
            preferences: {
                avoid_tolls: preferences.avoidTolls,
                prefer_highways: preferences.preferHighways,
                music_genre: preferences.musicGenre,
                wallet_address: wallet.address
            }
        })
    });

    const data = await response.json();
    return data.route; // Optimized route with waypoints
}
```

---

### 2.3 CarPlay Integration

**Manifest** (`Info.plist`):
```xml
<key>UIBackgroundModes</key>
<array>
    <string>audio</string>
</array>
<key>NSAppleMusicUsageDescription</key>
<string>Play Thronos music tracks</string>
```

**Template Support**:
```swift
import CarPlay

class CarPlaySceneDelegate: UIResponder, CPTemplateApplicationSceneDelegate {
    var interfaceController: CPInterfaceController?

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                 didConnect interfaceController: CPInterfaceController) {
        self.interfaceController = interfaceController

        // Create music list
        let musicList = CPListTemplate(
            title: "Thronos Music",
            sections: [createPlaylistSection(), createLibrarySection()]
        )

        interfaceController.setRootTemplate(musicList, animated: true)
    }

    func createPlaylistSection() -> CPListSection {
        let playlists = MusicModule.getPlaylists()

        let items = playlists.map { playlist in
            CPListItem(
                text: playlist.name,
                detailText: "\(playlist.tracks.count) tracks"
            )
        }

        return CPListSection(items: items)
    }
}
```

---

### 2.4 Android Auto Integration

**Manifest** (`AndroidManifest.xml`):
```xml
<application>
    <service android:name=".MusicService" android:exported="true">
        <intent-filter>
            <action android:name="android.media.browse.MediaBrowserService" />
        </intent-filter>
    </service>

    <meta-data
        android:name="com.google.android.gms.car.application"
        android:resource="@xml/automotive_app_desc" />
</application>
```

**Media Browser Service**:
```kotlin
class MusicService : MediaBrowserServiceCompat() {
    private lateinit var mediaSession: MediaSessionCompat

    override fun onCreate() {
        super.onCreate()

        mediaSession = MediaSessionCompat(this, "ThronosMusic").apply {
            setCallback(MediaSessionCallback())
            setFlags(MediaSessionCompat.FLAG_HANDLES_MEDIA_BUTTONS or
                    MediaSessionCompat.FLAG_HANDLES_TRANSPORT_CONTROLS)
        }

        sessionToken = mediaSession.sessionToken
    }

    override fun onGetRoot(clientPackageName: String,
                          clientUid: Int,
                          rootHints: Bundle?): BrowserRoot {
        return BrowserRoot("root", null)
    }

    override fun onLoadChildren(parentId: String,
                               result: Result<MutableList<MediaBrowserCompat.MediaItem>>) {
        val mediaItems = when (parentId) {
            "root" -> createRootItems()
            "playlists" -> createPlaylistItems()
            "library" -> createLibraryItems()
            else -> emptyList()
        }

        result.sendResult(mediaItems.toMutableList())
    }
}
```

---

## 3. Mobile App Structure

### 3.1 Android App
**Package Structure**:
```
com.thronos.wallet/
├── ui/
│   ├── MainActivity.kt
│   ├── WalletFragment.kt
│   ├── MusicFragment.kt
│   ├── TransactionsFragment.kt
│   └── SettingsFragment.kt
├── sdk/
│   ├── WalletSDK.kt
│   ├── MusicModule.kt
│   └── AuthModule.kt
├── services/
│   ├── MusicService.kt (MediaBrowserService)
│   ├── LocationService.kt (GPS telemetry)
│   └── SyncService.kt (Background sync)
├── models/
│   ├── Wallet.kt
│   ├── Transaction.kt
│   ├── Track.kt
│   └── Playlist.kt
└── utils/
    ├── CryptoUtils.kt
    ├── NetworkUtils.kt
    └── StorageUtils.kt
```

**Gradle Dependencies**:
```gradle
dependencies {
    // Core Android
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'

    // Media
    implementation 'androidx.media:media:1.7.0'

    // Location
    implementation 'com.google.android.gms:play-services-location:21.0.1'

    // Networking
    implementation 'com.squareup.okhttp3:okhttp:4.12.0'
    implementation 'com.squareup.retrofit2:retrofit:2.9.0'

    // Crypto
    implementation 'org.bouncycastle:bcprov-jdk15on:1.70'

    // Android Auto
    implementation 'androidx.car.app:app:1.3.0'
}
```

---

### 3.2 iOS App
**Project Structure**:
```
ThronosWallet/
├── UI/
│   ├── ContentView.swift
│   ├── WalletView.swift
│   ├── MusicView.swift
│   ├── TransactionsView.swift
│   └── SettingsView.swift
├── SDK/
│   ├── WalletSDK.swift
│   ├── MusicModule.swift
│   └── AuthModule.swift
├── Services/
│   ├── AudioPlayer.swift (AVPlayer)
│   ├── LocationManager.swift (CoreLocation)
│   └── SyncManager.swift (Background sync)
├── Models/
│   ├── Wallet.swift
│   ├── Transaction.swift
│   ├── Track.swift
│   └── Playlist.swift
└── Utils/
    ├── CryptoUtils.swift
    ├── NetworkUtils.swift
    └── StorageUtils.swift
```

**Package Dependencies** (`Package.swift`):
```swift
dependencies: [
    .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.8.0"),
    .package(url: "https://github.com/krzyzanowskim/CryptoSwift.git", from: "1.8.0"),
    .package(url: "https://github.com/apple/swift-protobuf.git", from: "1.25.0")
]
```

---

## 4. API Endpoints για SDKs

### 4.1 Wallet Endpoints
```
GET  /api/wallet/balance/{address}
GET  /api/wallet/transactions/{address}
POST /api/wallet/send
POST /api/wallet/receive
GET  /api/wallet/tokens/{address}
```

### 4.2 Music Endpoints
```
GET  /api/v1/music/tracks
GET  /api/v1/music/artist/{address}
POST /api/v1/music/play/{track_id}
POST /api/v1/music/tip

GET  /api/music/playlists?address={address}
POST /api/music/playlist/update
GET  /api/music/offline/{address}
POST /api/music/offline
```

### 4.3 Telemetry Endpoints
```
POST /api/telemetry/gps
GET  /api/telemetry/routes/{address}
POST /api/autopilot/route
GET  /api/autopilot/model
```

---

## 5. Deployment

### 5.1 Google Play Store
**Checklist**:
- ✅ App signing με Play App Signing
- ✅ Privacy policy URL
- ✅ Content rating questionnaire
- ✅ Screenshots (phone, tablet, Android Auto)
- ✅ Feature graphic (1024x500)
- ✅ Store listing translations (Greek, English)

**Release APK**:
```bash
# Build release APK
./gradlew assembleRelease

# Upload to Play Console
# https://play.google.com/console/
```

---

### 5.2 Apple App Store
**Checklist**:
- ✅ App Store Connect account
- ✅ Privacy policy URL
- ✅ App review information
- ✅ Screenshots (iPhone, iPad, CarPlay)
- ✅ App icon (1024x1024)
- ✅ Localizations (Greek, English)

**Release IPA**:
```bash
# Archive app
xcodebuild archive -workspace ThronosWallet.xcworkspace \
                   -scheme ThronosWallet \
                   -archivePath build/ThronosWallet.xcarchive

# Export IPA
xcodebuild -exportArchive -archivePath build/ThronosWallet.xcarchive \
                          -exportPath build/ \
                          -exportOptionsPlist ExportOptions.plist
```

---

## 6. Testing

### 6.1 Unit Tests
```kotlin
// Android
@Test
fun testWalletConnection() {
    val wallet = WalletSDK.getInstance(context)
    val result = wallet.connect(testAddress, testAuthSecret)
    assertTrue(result.isSuccess)
}
```

```swift
// iOS
func testWalletConnection() {
    let wallet = ThronosWallet.shared
    let expectation = self.expectation(description: "Wallet connection")

    wallet.connect(address: testAddress, authSecret: testAuthSecret) { result in
        XCTAssertTrue(result.isSuccess)
        expectation.fulfill()
    }

    waitForExpectations(timeout: 5)
}
```

### 6.2 CarPlay/Android Auto Testing
```bash
# Android Auto
# Connect device via USB and enable Developer mode in Android Auto app

# CarPlay Simulator
# Xcode > Open Developer Tool > CarPlay Simulator
```

---

## 7. Roadmap

### Phase 1: Core SDKs (✅ Complete)
- ✅ Wallet SDK
- ✅ Music Module
- ✅ Authentication SDK
- ✅ MediaSession API integration

### Phase 2: Mobile Apps (In Progress)
- 🔄 Android app development
- 🔄 iOS app development
- 🔄 CarPlay integration
- 🔄 Android Auto integration

### Phase 3: Telemetry & Autopilot (Planned)
- 📋 GPS telemetry collection
- 📋 Route optimization ML model
- 📋 Autopilot training pipeline
- 📋 Real-time route recommendations

### Phase 4: Distribution (Planned)
- 📋 Google Play Store submission
- 📋 Apple App Store submission
- 📋 Beta testing program
- 📋 Production release

---

## 8. Contributing

Για να συνεισφέρετε στα SDKs:
1. Fork το repository
2. Δημιουργήστε feature branch (`git checkout -b feature/new-sdk`)
3. Commit τις αλλαγές (`git commit -m 'Add new SDK feature'`)
4. Push στο branch (`git push origin feature/new-sdk`)
5. Ανοίξτε Pull Request

To contribute to the SDKs:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-sdk`)
3. Commit your changes (`git commit -m 'Add new SDK feature'`)
4. Push to the branch (`git push origin feature/new-sdk`)
5. Open a Pull Request

---

## Support

- **Documentation**: https://docs.thronos.network
- **GitHub Issues**: https://github.com/Tsipchain/thronos-V3.6/issues
- **Email**: dev@thronos.network

---

**Version**: 1.0.0
**Last Updated**: 2026-01-10
**License**: MIT
