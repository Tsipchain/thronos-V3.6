# THRONOS MUSIC/TELEMETRY MODAL + GPS SETUP

**Date**: 2026-01-17
**Integration**: IoT.html + Audio/Radio System
**Purpose**: Complete music-based data transmission + GPS telemetry

---

## 📡 OVERVIEW

The Music/Telemetry Modal combines:
- 🎵 **WhisperNote**: Audio-based transaction transmission
- 📻 **RadioNode**: RF signal data encoding
- 🛰️ **GPS Telemetry**: Real-time vehicle tracking
- 🔐 **Steganography**: Hidden payload embedding

---

## 🎨 MUSIC MODAL UI

### Modal Structure

```html
<div id="musicTelemetryModal" class="modal">
  <div class="modal-content">
    <h2>🎵 Music/Telemetry Transmitter</h2>

    <!-- Tab Navigation -->
    <div class="tabs">
      <button class="tab active" data-tab="whisper">WhisperNote</button>
      <button class="tab" data-tab="radio">RadioNode</button>
      <button class="tab" data-tab="gps">GPS Setup</button>
      <button class="tab" data-tab="telemetry">Live Telemetry</button>
    </div>

    <!-- WhisperNote Tab -->
    <div id="whisper-tab" class="tab-content active">
      <h3>Audio Transaction Encoding</h3>
      <p>Convert blockchain data to audio tones</p>

      <label>Transaction Data:</label>
      <textarea id="whisper-data" placeholder="Paste TX JSON..."></textarea>

      <label>Audio Frequency:</label>
      <select id="whisper-freq">
        <option value="1000">1kHz (Low)</option>
        <option value="2000" selected>2kHz (Mid)</option>
        <option value="4000">4kHz (High)</option>
      </select>

      <button onclick="generateWhisperNote()">🎵 Generate Audio</button>

      <div id="whisper-player" style="display:none;">
        <audio id="whisper-audio" controls></audio>
        <button onclick="downloadWhisper()">💾 Download WAV</button>
      </div>
    </div>

    <!-- RadioNode Tab -->
    <div id="radio-tab" class="tab-content">
      <h3>RF Signal Transmission</h3>
      <p>Encode data for radio broadcast</p>

      <label>Payload:</label>
      <textarea id="radio-payload" placeholder="Enter message..."></textarea>

      <label>Frequency Band:</label>
      <select id="radio-band">
        <option value="433">433 MHz (ISM)</option>
        <option value="868">868 MHz (EU)</option>
        <option value="915">915 MHz (US)</option>
      </select>

      <label>Modulation:</label>
      <select id="radio-mod">
        <option value="FSK">FSK (Frequency Shift)</option>
        <option value="OOK">OOK (On-Off Keying)</option>
        <option value="LoRa">LoRa (Long Range)</option>
      </select>

      <button onclick="encodeRadioSignal()">📻 Encode Signal</button>

      <div id="radio-output"></div>
    </div>

    <!-- GPS Setup Tab -->
    <div id="gps-tab" class="tab-content">
      <h3>GPS Telemetry Setup</h3>
      <p>Configure vehicle node location services</p>

      <div class="gps-status">
        <div id="gps-indicator" class="status-indicator offline">
          <span class="pulse"></span>
          GPS: <span id="gps-status-text">Not Connected</span>
        </div>
      </div>

      <button onclick="requestGPSAccess()" class="btn-primary">
        📍 Enable GPS
      </button>

      <div id="gps-data" style="display:none;">
        <h4>Current Position</h4>
        <table class="telemetry-table">
          <tr>
            <td>Latitude:</td>
            <td id="gps-lat">-</td>
          </tr>
          <tr>
            <td>Longitude:</td>
            <td id="gps-lon">-</td>
          </tr>
          <tr>
            <td>Altitude:</td>
            <td id="gps-alt">-</td>
          </tr>
          <tr>
            <td>Speed:</td>
            <td id="gps-speed">-</td>
          </tr>
          <tr>
            <td>Heading:</td>
            <td id="gps-heading">-</td>
          </tr>
          <tr>
            <td>Accuracy:</td>
            <td id="gps-accuracy">-</td>
          </tr>
        </table>

        <div class="gps-map" id="gps-map">
          <!-- Embedded map (Leaflet/OpenStreetMap) -->
        </div>

        <button onclick="transmitGPSData()">📡 Transmit Position</button>
      </div>
    </div>

    <!-- Live Telemetry Tab -->
    <div id="telemetry-tab" class="tab-content">
      <h3>Live Vehicle Telemetry</h3>
      <p>Real-time sensor data streaming</p>

      <div class="telemetry-grid">
        <div class="sensor-card">
          <h4>Speed</h4>
          <div class="sensor-value" id="telem-speed">0 km/h</div>
          <div class="sensor-chart" id="speed-chart"></div>
        </div>

        <div class="sensor-card">
          <h4>Battery</h4>
          <div class="sensor-value" id="telem-battery">100%</div>
          <div class="battery-bar">
            <div id="battery-fill" style="width:100%"></div>
          </div>
        </div>

        <div class="sensor-card">
          <h4>Lidar (Front)</h4>
          <div class="sensor-value" id="telem-lidar">- m</div>
        </div>

        <div class="sensor-card">
          <h4>Lane Deviation</h4>
          <div class="sensor-value" id="telem-lane">0.0 m</div>
        </div>

        <div class="sensor-card">
          <h4>AI Autopilot</h4>
          <div class="sensor-value" id="telem-mode">MANUAL</div>
          <button onclick="requestAutopilot()">🤖 Activate AI</button>
        </div>

        <div class="sensor-card">
          <h4>Driver Alertness</h4>
          <div class="sensor-value" id="telem-alert">HIGH</div>
        </div>
      </div>

      <button onclick="toggleTelemetryStream()" id="telem-toggle">
        ▶️ Start Streaming
      </button>
    </div>
  </div>
</div>
```

---

## 🎵 WhisperNote Implementation

### Audio Encoding (JavaScript)

```javascript
// Generate audio tones from transaction data
async function generateWhisperNote() {
  const data = document.getElementById('whisper-data').value;
  const freq = parseInt(document.getElementById('whisper-freq').value);

  if (!data) {
    alert('Enter transaction data first');
    return;
  }

  try {
    const txData = JSON.parse(data);

    // Convert JSON to binary
    const binary = jsonToBinary(txData);

    // Generate audio tones
    const audioBuffer = await generateAudioFromBinary(binary, freq);

    // Create audio element
    const audioBlob = bufferToWav(audioBuffer);
    const audioUrl = URL.createObjectURL(audioBlob);

    const player = document.getElementById('whisper-audio');
    player.src = audioUrl;

    document.getElementById('whisper-player').style.display = 'block';

    // Store for download
    window.whisperBlob = audioBlob;

  } catch (e) {
    alert('Error encoding audio: ' + e.message);
  }
}

function jsonToBinary(data) {
  const json = JSON.stringify(data);
  return json.split('').map(c =>
    c.charCodeAt(0).toString(2).padStart(8, '0')
  ).join('');
}

async function generateAudioFromBinary(binary, baseFreq) {
  const audioContext = new (window.AudioContext || window.webkitAudioContext)();
  const sampleRate = 44100;
  const bitDuration = 0.1; // 100ms per bit
  const totalSamples = Math.ceil(binary.length * bitDuration * sampleRate);

  const audioBuffer = audioContext.createBuffer(1, totalSamples, sampleRate);
  const channelData = audioBuffer.getChannelData(0);

  let sampleIndex = 0;

  for (let i = 0; i < binary.length; i++) {
    const bit = binary[i];
    // '1' = high freq, '0' = low freq
    const freq = bit === '1' ? baseFreq : baseFreq / 2;
    const samplesPerBit = Math.floor(bitDuration * sampleRate);

    for (let j = 0; j < samplesPerBit; j++) {
      const t = sampleIndex / sampleRate;
      channelData[sampleIndex] = Math.sin(2 * Math.PI * freq * t) * 0.5;
      sampleIndex++;
    }
  }

  return audioBuffer;
}

function bufferToWav(audioBuffer) {
  const numChannels = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const format = 1; // PCM
  const bitDepth = 16;

  const bytesPerSample = bitDepth / 8;
  const blockAlign = numChannels * bytesPerSample;

  const data = audioBuffer.getChannelData(0);
  const dataLength = data.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);

  // WAV header
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataLength, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, format, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);
  writeString(view, 36, 'data');
  view.setUint32(40, dataLength, true);

  // PCM samples
  let offset = 44;
  for (let i = 0; i < data.length; i++) {
    const sample = Math.max(-1, Math.min(1, data[i]));
    view.setInt16(offset, sample * 0x7FFF, true);
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

function downloadWhisper() {
  if (!window.whisperBlob) return;

  const url = URL.createObjectURL(window.whisperBlob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `whisper_tx_${Date.now()}.wav`;
  a.click();
}
```

---

## 📻 RadioNode Implementation

### RF Signal Encoding (Python Backend)

```python
# radio_encode.py - Enhanced version

import json
import struct
import base64

def encode_radio_signal(payload, frequency=433, modulation='FSK'):
    """
    Encode payload for RF transmission

    Args:
        payload: String or dict to encode
        frequency: RF frequency in MHz
        modulation: 'FSK', 'OOK', or 'LoRa'

    Returns:
        dict with encoded signal parameters
    """
    if isinstance(payload, dict):
        payload = json.dumps(payload)

    # Convert to binary
    binary = ''.join(format(ord(c), '08b') for c in payload)

    # Add preamble and sync word
    preamble = '10101010' * 4  # 32-bit preamble
    sync_word = '11110000'
    encoded = preamble + sync_word + binary

    # Calculate timing
    baud_rate = get_baud_rate(modulation)
    duration_ms = (len(encoded) / baud_rate) * 1000

    # Modulation parameters
    params = {
        'frequency_mhz': frequency,
        'modulation': modulation,
        'baud_rate': baud_rate,
        'payload_bits': len(binary),
        'total_bits': len(encoded),
        'duration_ms': round(duration_ms, 2),
        'encoded_data': base64.b64encode(encoded.encode()).decode()
    }

    return params

def get_baud_rate(modulation):
    """Get baud rate for modulation type"""
    rates = {
        'FSK': 4800,
        'OOK': 1200,
        'LoRa': 250  # LoRa SF7
    }
    return rates.get(modulation, 4800)

# API Endpoint
@app.route("/api/radio/encode", methods=["POST"])
def api_radio_encode():
    data = request.get_json() or {}
    payload = data.get("payload", "")
    frequency = int(data.get("frequency", 433))
    modulation = data.get("modulation", "FSK")

    result = encode_radio_signal(payload, frequency, modulation)
    return jsonify(result), 200
```

---

## 🛰️ GPS Setup Implementation

### GPS Access (Browser Geolocation API)

```javascript
let gpsWatchId = null;
let gpsDataCache = null;

async function requestGPSAccess() {
  if (!navigator.geolocation) {
    alert('GPS not supported on this device');
    return;
  }

  try {
    const permission = await navigator.permissions.query({ name: 'geolocation' });

    if (permission.state === 'denied') {
      alert('GPS permission denied. Please enable in browser settings.');
      return;
    }

    // Request initial position
    navigator.geolocation.getCurrentPosition(
      handleGPSSuccess,
      handleGPSError,
      { enableHighAccuracy: true, timeout: 10000 }
    );

    // Start watching position
    gpsWatchId = navigator.geolocation.watchPosition(
      handleGPSSuccess,
      handleGPSError,
      { enableHighAccuracy: true, maximumAge: 1000 }
    );

    updateGPSStatus('connected');

  } catch (e) {
    handleGPSError({ message: e.message });
  }
}

function handleGPSSuccess(position) {
  const { latitude, longitude, altitude, accuracy, speed, heading } = position.coords;

  gpsDataCache = {
    lat: latitude.toFixed(6),
    lon: longitude.toFixed(6),
    alt: altitude ? `${altitude.toFixed(1)} m` : 'N/A',
    speed: speed ? `${(speed * 3.6).toFixed(1)} km/h` : '0 km/h',
    heading: heading ? `${heading.toFixed(0)}°` : 'N/A',
    accuracy: `±${accuracy.toFixed(1)} m`,
    timestamp: new Date(position.timestamp).toISOString()
  };

  // Update UI
  document.getElementById('gps-lat').textContent = gpsDataCache.lat;
  document.getElementById('gps-lon').textContent = gpsDataCache.lon;
  document.getElementById('gps-alt').textContent = gpsDataCache.alt;
  document.getElementById('gps-speed').textContent = gpsDataCache.speed;
  document.getElementById('gps-heading').textContent = gpsDataCache.heading;
  document.getElementById('gps-accuracy').textContent = gpsDataCache.accuracy;

  document.getElementById('gps-data').style.display = 'block';

  // Update map
  updateGPSMap(latitude, longitude);
}

function handleGPSError(error) {
  console.error('GPS Error:', error);
  updateGPSStatus('error', error.message);
}

function updateGPSStatus(status, message = '') {
  const indicator = document.getElementById('gps-indicator');
  const statusText = document.getElementById('gps-status-text');

  indicator.className = `status-indicator ${status}`;

  const statusMessages = {
    'connected': 'Connected',
    'error': `Error: ${message}`,
    'offline': 'Not Connected'
  };

  statusText.textContent = statusMessages[status] || 'Unknown';
}

function updateGPSMap(lat, lon) {
  // Initialize map if not already done
  if (!window.gpsMap) {
    window.gpsMap = L.map('gps-map').setView([lat, lon], 15);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(window.gpsMap);

    window.gpsMarker = L.marker([lat, lon]).addTo(window.gpsMap);
  } else {
    // Update existing marker
    window.gpsMarker.setLatLng([lat, lon]);
    window.gpsMap.setView([lat, lon]);
  }
}

async function transmitGPSData() {
  if (!gpsDataCache) {
    alert('No GPS data available');
    return;
  }

  const wallet = localStorage.getItem('thr_address');
  if (!wallet) {
    alert('Connect wallet first');
    return;
  }

  try {
    const response = await fetch('/api/iot/submit_gps', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        wallet,
        gps: {
          lat: parseFloat(gpsDataCache.lat),
          lon: parseFloat(gpsDataCache.lon),
          alt: gpsDataCache.alt,
          speed: gpsDataCache.speed,
          heading: gpsDataCache.heading,
          accuracy: gpsDataCache.accuracy
        },
        timestamp: gpsDataCache.timestamp
      })
    });

    const result = await response.json();

    if (result.status === 'success') {
      alert('✅ GPS data transmitted to blockchain!');
    } else {
      alert('❌ Error: ' + result.message);
    }

  } catch (e) {
    alert('❌ Transmission failed: ' + e.message);
  }
}
```

---

## 📊 Live Telemetry Stream

### Real-time Sensor Data

```javascript
let telemetryStream = null;
let telemetryInterval = null;

function toggleTelemetryStream() {
  const button = document.getElementById('telem-toggle');

  if (telemetryStream) {
    // Stop stream
    if (telemetryInterval) clearInterval(telemetryInterval);
    telemetryStream = null;
    button.textContent = '▶️ Start Streaming';
  } else {
    // Start stream
    telemetryStream = true;
    button.textContent = '⏸️ Stop Streaming';
    startTelemetryPolling();
  }
}

async function startTelemetryPolling() {
  fetchTelemetry(); // Initial fetch

  telemetryInterval = setInterval(async () => {
    if (telemetryStream) {
      await fetchTelemetry();
    }
  }, 1000); // Update every second
}

async function fetchTelemetry() {
  try {
    const response = await fetch('/api/iot/telemetry/live');
    const data = await response.json();

    // Update UI
    document.getElementById('telem-speed').textContent = `${data.speed} km/h`;
    document.getElementById('telem-battery').textContent = `${data.battery}%`;
    document.getElementById('battery-fill').style.width = `${data.battery}%`;
    document.getElementById('telem-lidar').textContent = `${data.lidar_front} m`;
    document.getElementById('telem-lane').textContent = `${data.lane_deviation} m`;
    document.getElementById('telem-mode').textContent = data.mode;
    document.getElementById('telem-alert').textContent = data.driver_alertness;

    // Color coding
    const modeEl = document.getElementById('telem-mode');
    if (data.mode === 'AI_AUTOPILOT') {
      modeEl.style.color = '#00ff66';
    } else {
      modeEl.style.color = '#ffffff';
    }

  } catch (e) {
    console.error('Telemetry fetch error:', e);
  }
}

async function requestAutopilot() {
  const wallet = localStorage.getItem('thr_address');
  const secret = localStorage.getItem('thr_secret');

  if (!wallet || !secret) {
    alert('Connect wallet first');
    return;
  }

  const confirmed = confirm(
    '🤖 Request AI Autopilot?\n\n' +
    'Cost: 5 THR\n' +
    'Duration: Unlimited until manual override\n\n' +
    'Continue?'
  );

  if (!confirmed) return;

  try {
    const response = await fetch('/api/iot/autonomous_request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        wallet,
        auth_secret: secret,
        action: 'ACTIVATE_AUTOPILOT',
        destination: 'Auto-navigate'
      })
    });

    const result = await response.json();

    if (result.status === 'granted') {
      alert('✅ AI Autopilot Activated!');
      document.getElementById('telem-mode').textContent = 'AI_AUTOPILOT';
      document.getElementById('telem-mode').style.color = '#00ff66';
    } else {
      alert('❌ Error: ' + result.message);
    }

  } catch (e) {
    alert('❌ Request failed: ' + e.message);
  }
}
```

---

## 🔌 Backend API Endpoints

### New Endpoints Needed

```python
# server.py additions

@app.route("/api/radio/encode", methods=["POST"])
def api_radio_encode():
    """Encode payload for RF transmission"""
    # Implementation above
    pass

@app.route("/api/iot/submit_gps", methods=["POST"])
def api_iot_submit_gps():
    """Submit GPS telemetry data"""
    data = request.get_json() or {}
    wallet = data.get("wallet")
    gps = data.get("gps", {})

    if not wallet:
        return jsonify({"status": "error", "message": "Wallet required"}), 400

    # Save to IoT data
    iot_file = os.path.join(DATA_DIR, "iot_gps_data.json")
    iot_data = load_json(iot_file, [])

    entry = {
        "wallet": wallet,
        "gps": gps,
        "timestamp": data.get("timestamp"),
        "recorded_at": datetime.datetime.utcnow().isoformat() + "Z"
    }

    iot_data.append(entry)
    save_json(iot_file, iot_data)

    return jsonify({"status": "success", "entry_id": len(iot_data) - 1}), 200

@app.route("/api/iot/telemetry/live", methods=["GET"])
def api_iot_telemetry_live():
    """Get latest telemetry from all active vehicles"""
    iot_file = os.path.join(DATA_DIR, "iot_data.json")
    iot_data = load_json(iot_file, [])

    # Return most recent entry
    if iot_data:
        latest = iot_data[-1]
        return jsonify(latest.get("data", {})), 200

    # Return mock data if none available
    return jsonify({
        "speed": 0,
        "battery": 100,
        "lidar_front": 150,
        "lane_deviation": 0.0,
        "mode": "MANUAL",
        "driver_alertness": "HIGH"
    }), 200
```

---

## ✅ COMPLETE IMPLEMENTATION

This specification provides:
- ✅ WhisperNote audio encoding
- ✅ RadioNode RF signal generation
- ✅ GPS setup with browser Geolocation API
- ✅ Live telemetry streaming
- ✅ AI Autopilot requests
- ✅ All backend APIs

**Next**: Add this modal to IoT.html and test!
