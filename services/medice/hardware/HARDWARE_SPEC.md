# ThronomedICE - Hardware Specification

## The Wearable Device

A child-safe IoT wristband that measures body temperature continuously
and transmits data via Bluetooth Low Energy (BLE) to the parent's phone.

---

## Bill of Materials (per unit)

| # | Component | Model | Purpose | Cost (1k units) |
|---|-----------|-------|---------|------------------|
| 1 | Microcontroller | **ESP32-S3 Mini** | BLE 5.0 + WiFi, ultra-low-power sleep | $3.50 |
| 2 | IR Thermometer | **MLX90614ESF-BAA** | Non-contact body temp, ±0.5°C accuracy | $8.00 |
| 3 | Battery | LiPo 3.7V 180mAh | Rechargeable, thin profile | $2.50 |
| 4 | Charge IC | TP4056 + USB-C | Safe LiPo charging via USB-C | $0.80 |
| 5 | PCB | Custom 2-layer | All components on 25×20mm board | $1.20 |
| 6 | Enclosure | Medical-grade silicone | Wristband, IP67, hypoallergenic | $4.00 |
| 7 | Assembly | SMT + test | - | $3.00 |
| | **Total** | | | **~$23 / unit** |

---

## Wiring Diagram

```
ESP32-S3 Mini        MLX90614
-----------          --------
GPIO 21 (SDA) -----> SDA
GPIO 22 (SCL) -----> SCL
3.3V          -----> VCC
GND           -----> GND

ESP32-S3 Mini        TP4056
-----------          ------
3.3V          <----- OUT+
GND           <----- OUT-
```

---

## Form Factor Options

### Option A - Wristband (recommended, age 2+)
- Soft silicone strap, 14-20 cm adjustable
- MLX90614 sensor window on inner wrist (radial artery)
- Wrist-to-oral temperature correction factor: **+0.3°C** applied in firmware

### Option B - Chest Patch (recommended, age 0-24 months)
- Medical-grade adhesive patch (hypoallergenic)
- Sensor 1-2mm from skin, taped flat
- Change patch every 48h

### Option C - Ear Clip (age 5+)
- Soft silicone clip over earlobe
- Most accurate reading for core temperature

---

## Power Budget

| Mode | Current Draw | Battery Life (180mAh) |
|------|-------------|----------------------|
| Active: BLE TX + Sensor | 80 mA | ~2.25 h |
| BLE advertising + ESP light-sleep | 8 mA | ~22 h |
| Deep sleep (wake every 5 min) | 0.15 mA peak avg | **~7 days** |

**Recommended duty cycle**: Deep sleep 4m55s, wake and measure 5s, transmit via BLE.

---

## Sensor Accuracy

- **MLX90614 spec**: ±0.5°C in 36–40°C range
- **Sample time**: 500ms per reading
- **Calibration**: Factory-calibrated; apply per-device offset stored in NVS
- **Wrist offset**: +0.3°C to match oral/axillary measurements (configurable)

---

## BLE Protocol

| Item | Value |
|------|-------|
| Service UUID | `4fafc201-1fb5-459e-8fcc-c5c9c331914b` |
| Temp Characteristic | `beb5483e-36e1-4688-b7f5-ea07361b26a8` (Notify) |
| Alert Characteristic | `beb5483e-36e1-4688-b7f5-ea07361b26a9` (Notify) |

### Payload (JSON, UTF-8 over BLE)

```json
{
  "device_id": "THRM-001",
  "object_temp": 38.52,
  "ambient_temp": 22.30,
  "ts": 1714512000
}
```

Alert characteristic payload:
```json
{ "alert": "FEVER", "temp": 38.52 }
```

---

## Data Flow

```
[ThronomedICE Chip]
       | BLE Notify every 5 min
       v
[Parent Mobile App]  <-- React Native, BLE listener
       | HTTPS POST /readings
       v
[ThronomedICE API]  (FastAPI)
       |---> FCM Push Notification  --> [Parent Phone]
       |---> Thronos Blockchain     --> [Immutable Record]
       |---> PostgreSQL DB          --> [Local History]
       |---> Hospital API           --> [Hospital System]
```

---

## Regulatory Requirements

| Market | Certification | Class |
|--------|--------------|-------|
| EU | CE + MDR (Medical Device Regulation) | Class IIa |
| USA | FDA 510(k) | Class II |
| Global | ISO 13485 (Quality Management) | - |
| Global | IEC 60601-1 (Electrical Safety) | - |

> **Note**: As a monitoring-only device (no active therapy), the regulatory
> pathway is simplified. Consult a Notified Body before CE marking.

---

## PCB Dimensions

- Board: 25 mm × 20 mm × 1.2 mm
- Wristband housing: 35 mm × 28 mm × 10 mm
- Total weight: ~18 g with battery
- Charging port: USB-C (bottom of housing)
