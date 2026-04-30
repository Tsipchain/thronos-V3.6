# ThronomedICE - IoT Temperature Monitoring Service

A medical IoT system that monitors a child's body temperature in real time,
alerts parents when fever is detected, records all fever history on the
**Thronos blockchain**, and provides a hospital integration API.

---

## System Architecture

```
┌──────────────────────┐
│  ThronomedICE Chip       │  ESP32-S3 + MLX90614 IR sensor
│  (Wristband / Patch)     │  wears on child's wrist
└─────────┬───────────┘
                 │ BLE 5.0 (every 5 min)
                 ▼
┌──────────────────────┐
│  Parent Mobile App       │  React Native, BLE listener
└─────────┬───────────┘
                 │ HTTPS POST /readings
                 ▼
┌──────────────────────┐
│  FastAPI Service          │  main.py
│  (TempMonitor)           │
└─┬───────────┬────┬──┘
    │            │         │
    ▼            ▼         ▼
┌───────┐  ┌────────┐  ┌──────────┐
│ FCM   │  │Thronos │  │Hospital  │
│ Push  │  │ Chain  │  │  API     │
│ Notif.│  │(Web3) │  │(guarded)│
└──┬──┘  └────────┘  └──────────┘
       │
       ▼
┌────────┐
│Parent  │ ← Alert on mobile
│ Phone  │
└────────┘
```

---

## Features

| Feature | Detail |
|---------|--------|
| Continuous monitoring | Reading every 5 minutes |
| Fever detection | Alert at 38.0°C (configurable) |
| High fever alert | Separate urgent alert at 39.0°C |
| Antipyretic reminder | Notification every 4 h while fever active |
| Fever history | Full timeline in PostgreSQL + Thronos blockchain |
| Blockchain security | Every fever event hash-stored; immutable audit trail |
| Hospital access | Guardian grants/revokes hospital read access |
| BLE or gateway | Mobile app BLE OR Raspberry Pi room gateway |

---

## Repository Structure

```
services/medice/
├── firmware/              # ESP32-S3 Arduino code
│   ├── src/
│   │   ├── thermometer_chip.ino
│   │   └── config.h
│   └── platformio.ini
├── contracts/             # Solidity smart contract
│   ├── FeverHistory.sol
│   └── deploy.py
├── hardware/
│   └── HARDWARE_SPEC.md     # BOM, wiring, form factors
├── main.py                # FastAPI app entry point
├── models.py              # SQLAlchemy + Pydantic models
├── fever_analyzer.py      # Fever state machine
├── blockchain.py          # Thronos Web3 integration
├── notifications.py       # FCM push notifications
├── ble_receiver.py        # Raspberry Pi BLE gateway
├── hospital_api.py        # Hospital read endpoints
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Fill in:
#   THRONOS_RPC_URL        = http://your-thronos-node:8545
#   MEDICE_PRIVATE_KEY     = 0x...    (service wallet private key)
#   FEVER_CONTRACT_ADDRESS = 0x...    (deployed FeverHistory.sol)
#   FCM_SERVER_KEY         = ...      (Firebase Cloud Messaging key)
#   HOSPITAL_API_KEY       = ...      (secret for hospital access)
```

### 2. Deploy the smart contract

```bash
cd contracts
# Compile first with solc or Hardhat, then:
python deploy.py
# Copy the printed contract address to FEVER_CONTRACT_ADDRESS
```

### 3. Run the service

```bash
docker-compose up -d
# Service runs on http://localhost:8000
# API docs: http://localhost:8000/docs
```

### 4. Flash the chip

```bash
cd firmware
pio run --target upload
```

---

## API Endpoints

### Guardian setup
```
POST /guardians               # Register parent with FCM token
PUT  /guardians/{id}/fcm-token # Update push token
POST /patients                # Register child + chip device_id
```

### Temperature readings (called by mobile app / BLE gateway)
```
POST /readings                # Submit a reading from the chip
```

### Fever history
```
GET  /patients/{id}/current-temp       # Latest reading + fever status
GET  /patients/{id}/fever-history      # All fever events (local DB)
GET  /patients/{id}/blockchain-history # Fever events from Thronos chain
PUT  /fever-events/{id}/antipyretic    # Confirm medication given
```

### Hospital integration
```
POST   /hospital/patients/{id}/access        # Grant hospital read access
DELETE /hospital/patients/{id}/access        # Revoke access
GET    /hospital/patients/{id}/fever-history  # Hospital reads history
GET    /hospital/patients/{id}/recent-readings
```

---

## Notification Flow

```
Temp reading arrives
       │
  ≥ 38.0°C ?
     │ YES
     ├── First time? ──> FEVER ALERT notification to parent
     │                    + Record FeverEvent on Thronos blockchain
     ├── ≥ 39.0°C?  ──> HIGH FEVER ALERT (urgent)
     └── 4h since last antipyretic? ──> ANTIPYRETIC REMINDER

6 consecutive normal readings (~30 min)
     └──> FEVER ENDED notification
         + Close FeverEvent on blockchain
```

---

## Blockchain Data Structure

Each `FeverEvent` on-chain stores:

| Field | Type | Example |
|-------|------|---------|
| `startTime` | uint256 | 1714512000 (unix ts) |
| `endTime` | uint256 | 1714523600 (0 = active) |
| `peakTemp` | uint256 | 3852 (= 38.52°C) |
| `antipyreticGiven` | bool | true |
| `isClosed` | bool | true |

Hospitals only see data **after the guardian grants access** via
`setHospitalAccess()` on the contract.

---

## Roadmap

- [x] ESP32 BLE firmware
- [x] FastAPI monitoring service
- [x] FCM push notifications
- [x] Thronos blockchain integration
- [x] Hospital API with access control
- [ ] React Native mobile app (BLE + notifications)
- [ ] OTA firmware updates over WiFi
- [ ] Multi-child support per guardian
- [ ] HL7 FHIR export for hospital EHR integration
- [ ] ECG / SpO2 sensor expansion module
