#pragma once

#define DEVICE_NAME   "ThronomedICE-01"
#define DEVICE_ID     "THRM-001"

// I2C pins for MLX90614
#define SDA_PIN 21
#define SCL_PIN 22

// Fever threshold degrees Celsius
#define FEVER_THRESHOLD 38.0f

// Measurement every 5 minutes (5000 for dev)
#define MEASUREMENT_INTERVAL_MS 300000UL

// BLE UUIDs - must match ble_receiver.py
#define TEMP_SERVICE_UUID         "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define TEMP_CHARACTERISTIC_UUID  "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define ALERT_CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a9"
