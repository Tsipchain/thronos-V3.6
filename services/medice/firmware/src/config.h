#pragma once

// ── BLE UUIDs ──────────────────────────────────────────────────────────────
#define TEMP_SERVICE_UUID          "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define TEMP_CHARACTERISTIC_UUID   "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define VITAL_CHARACTERISTIC_UUID  "beb5483e-36e1-4688-b7f5-ea07361b26aa"
#define ALERT_CHARACTERISTIC_UUID  "beb5483e-36e1-4688-b7f5-ea07361b26a9"

// ── MLX90614 (IR Thermometer) ───────────────────────────────────────────────
#define FEVER_THRESHOLD        38.0f
#define HIGH_FEVER_THRESHOLD   39.0f
#define MEASUREMENT_INTERVAL_MS  300000UL  // 5 minutes

// ── MAX30102 (Pulse Oximeter) ──────────────────────────────────────────────
#define MAX30102_I2C_ADDR      0x57
#define SPO2_LOW_THRESHOLD     94.0f   // alert below 94%
#define SPO2_CRITICAL          90.0f   // urgent below 90%
#define BPM_LOW_CHILD          60      // bradycardia threshold
#define BPM_HIGH_CHILD        130      // tachycardia threshold
#define SPO2_SAMPLE_WINDOW      5      // seconds of samples to average
#define VITAL_INTERVAL_MS   60000UL   // pulse read every 1 minute

// ── Device ─────────────────────────────────────────────────────────────────
#define DEVICE_NAME            "ThronomedICE"
#define BATTERY_PIN            A0
