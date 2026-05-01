#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>
#include <MAX30105.h>          // SparkFun MAX3010x library
#include <heartRate.h>
#include <spo2_algorithm.h>
#include <ArduinoJson.h>
#include "config.h"

// ── BLE ────────────────────────────────────────────────────────────────────
NimBLEServer*         pServer         = nullptr;
NimBLECharacteristic* pTempChar       = nullptr;
NimBLECharacteristic* pVitalChar      = nullptr;
NimBLECharacteristic* pAlertChar      = nullptr;
bool                  deviceConnected = false;

// ── Sensors ────────────────────────────────────────────────────────────────
Adafruit_MLX90614 mlx;
MAX30105          particleSensor;

// ── Timing ─────────────────────────────────────────────────────────────────
unsigned long lastTempMs  = 0;
unsigned long lastVitalMs = 0;

// ── SpO2 buffers (MAX30102 algo needs 100 samples) ─────────────────────────
uint32_t irBuffer[100],  redBuffer[100];
int32_t  spo2;           int8_t  validSPO2;
int32_t  heartRate;      int8_t  validHR;

class ConnectCB : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer*) override    { deviceConnected = true; }
  void onDisconnect(NimBLEServer*) override {
    deviceConnected = false;
    NimBLEDevice::startAdvertising();
  }
};

void setupBLE() {
  NimBLEDevice::init(DEVICE_NAME);
  pServer = NimBLEDevice::createServer();
  pServer->setCallbacks(new ConnectCB());

  auto* svc   = pServer->createService(TEMP_SERVICE_UUID);
  pTempChar   = svc->createCharacteristic(TEMP_CHARACTERISTIC_UUID,
                  NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  pVitalChar  = svc->createCharacteristic(VITAL_CHARACTERISTIC_UUID,
                  NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  pAlertChar  = svc->createCharacteristic(ALERT_CHARACTERISTIC_UUID,
                  NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  svc->start();

  auto* adv = NimBLEDevice::getAdvertising();
  adv->addServiceUUID(TEMP_SERVICE_UUID);
  adv->start();
}

bool setupMAX30102() {
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) return false;
  particleSensor.setup(60, 4, 2, 200, 411, 4096);  // brightness, avg, mode, rate, width, ADC
  particleSensor.setPulseAmplitudeRed(0x0A);
  particleSensor.setPulseAmplitudeGreen(0);
  return true;
}

void readSpO2() {
  // Fill 100-sample buffer
  for (byte i = 0; i < 100; i++) {
    while (!particleSensor.available()) particleSensor.check();
    redBuffer[i] = particleSensor.getRed();
    irBuffer[i]  = particleSensor.getIR();
    particleSensor.nextSample();
  }
  maxim_heart_rate_and_oxygen_saturation(
    irBuffer, 100, redBuffer, &spo2, &validSPO2, &heartRate, &validHR);
}

void sendVitalJSON(float tempC) {
  StaticJsonDocument<256> doc;
  doc["temperature"]  = tempC;
  doc["spo2"]         = validSPO2 ? spo2  : -1;
  doc["bpm"]          = validHR   ? heartRate : -1;
  doc["spo2_valid"]   = (bool)validSPO2;
  doc["bpm_valid"]    = (bool)validHR;
  doc["ts"]           = millis();

  char buf[256];
  serializeJson(doc, buf);
  pTempChar->setValue((uint8_t*)buf, strlen(buf));
  pTempChar->notify();

  // Vital char gets compact SpO2+BPM only
  StaticJsonDocument<128> vdoc;
  vdoc["spo2"] = validSPO2 ? spo2      : -1;
  vdoc["bpm"]  = validHR   ? heartRate : -1;
  char vbuf[128];
  serializeJson(vdoc, vbuf);
  pVitalChar->setValue((uint8_t*)vbuf, strlen(vbuf));
  pVitalChar->notify();
}

void sendAlert(const char* type, float value) {
  StaticJsonDocument<128> doc;
  doc["alert"] = type;
  doc["value"] = value;
  char buf[128];
  serializeJson(doc, buf);
  pAlertChar->setValue((uint8_t*)buf, strlen(buf));
  pAlertChar->notify();
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  setupBLE();

  if (!mlx.begin()) Serial.println("MLX90614 not found");
  if (!setupMAX30102()) Serial.println("MAX30102 not found");

  Serial.println("ThronomedICE ready");
}

void loop() {
  unsigned long now = millis();

  // ── Temperature (every 5 min) ───────────────────────────────────────────
  if (now - lastTempMs >= MEASUREMENT_INTERVAL_MS) {
    lastTempMs = now;
    float tempC = mlx.readObjectTempC();

    if (!isnan(tempC)) {
      readSpO2();
      if (deviceConnected) sendVitalJSON(tempC);

      if (tempC >= HIGH_FEVER_THRESHOLD)
        sendAlert("HIGH_FEVER", tempC);
      else if (tempC >= FEVER_THRESHOLD)
        sendAlert("FEVER", tempC);

      if (validSPO2 && spo2 < SPO2_CRITICAL)
        sendAlert("SPO2_CRITICAL", spo2);
      else if (validSPO2 && spo2 < SPO2_LOW_THRESHOLD)
        sendAlert("SPO2_LOW", spo2);

      if (validHR && (heartRate < BPM_LOW_CHILD || heartRate > BPM_HIGH_CHILD))
        sendAlert("HR_ABNORMAL", heartRate);
    }
  }

  // ── Pulse quick-check (every 1 min, light sampling) ────────────────────
  if (now - lastVitalMs >= VITAL_INTERVAL_MS) {
    lastVitalMs = now;
    readSpO2();
    if (deviceConnected && (validSPO2 || validHR)) {
      StaticJsonDocument<128> vdoc;
      vdoc["spo2"] = validSPO2 ? spo2      : -1;
      vdoc["bpm"]  = validHR   ? heartRate : -1;
      char vbuf[128];
      serializeJson(vdoc, vbuf);
      pVitalChar->setValue((uint8_t*)vbuf, strlen(vbuf));
      pVitalChar->notify();
    }
  }
}
