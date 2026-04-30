#include <Arduino.h>
#include <NimBLEDevice.h>
#include <NimBLEServer.h>
#include <NimBLEUtils.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>
#include "config.h"

Adafruit_MLX90614 mlx;
NimBLEServer*         pServer   = nullptr;
NimBLECharacteristic* pTempChar  = nullptr;
NimBLECharacteristic* pAlertChar = nullptr;
bool     deviceConnected = false;
uint32_t lastMeasureTime = 0;

class ConnCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* s) override {
        deviceConnected = true;
        Serial.println("Mobile app connected");
    }
    void onDisconnect(NimBLEServer* s) override {
        deviceConnected = false;
        NimBLEDevice::startAdvertising();
    }
};

void setupBLE() {
    NimBLEDevice::init(DEVICE_NAME);
    NimBLEDevice::setPower(ESP_PWR_LVL_P9);

    pServer = NimBLEDevice::createServer();
    pServer->setCallbacks(new ConnCallbacks());

    NimBLEService* pSvc = pServer->createService(TEMP_SERVICE_UUID);

    pTempChar = pSvc->createCharacteristic(
        TEMP_CHARACTERISTIC_UUID,
        NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
    );
    pAlertChar = pSvc->createCharacteristic(
        ALERT_CHARACTERISTIC_UUID,
        NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
    );

    pSvc->start();

    NimBLEAdvertising* pAdv = NimBLEDevice::getAdvertising();
    pAdv->addServiceUUID(TEMP_SERVICE_UUID);
    pAdv->setScanResponse(true);
    NimBLEDevice::startAdvertising();

    Serial.println("BLE advertising started");
}

void setup() {
    Serial.begin(115200);
    Wire.begin(SDA_PIN, SCL_PIN);

    if (!mlx.begin()) {
        Serial.println("FATAL: MLX90614 sensor not found - check wiring");
        while (true) delay(1000);
    }
    Serial.printf("MLX90614 ready. Ambient: %.2f C\n", mlx.readAmbientTempC());

    setupBLE();
    Serial.println("ThronomedICE ready");
}

void loop() {
    uint32_t now = millis();

    // Wait for connection and interval
    if (!deviceConnected || (now - lastMeasureTime < MEASUREMENT_INTERVAL_MS)) {
        delay(100);
        return;
    }
    lastMeasureTime = now;

    float objTemp = mlx.readObjectTempC();
    float ambTemp = mlx.readAmbientTempC();

    // JSON payload to mobile app
    char buf[160];
    snprintf(buf, sizeof(buf),
        "{\"device_id\":\"%s\",\"object_temp\":%.2f,\"ambient_temp\":%.2f,\"ts\":%lu}",
        DEVICE_ID, objTemp, ambTemp, (unsigned long)(now / 1000));

    pTempChar->setValue(buf);
    pTempChar->notify();
    Serial.printf("Sent: %s\n", buf);

    // Immediate alert on fever
    if (objTemp >= FEVER_THRESHOLD) {
        char alert[64];
        snprintf(alert, sizeof(alert),
            "{\"alert\":\"FEVER\",\"temp\":%.2f}", objTemp);
        pAlertChar->setValue(alert);
        pAlertChar->notify();
        Serial.printf("FEVER ALERT sent: %.2f C\n", objTemp);
    }
}
