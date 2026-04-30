import React, { createContext, useEffect, useRef, useState } from "react";
import { BleManager, Device } from "react-native-ble-plx";
import { useContext } from "react";
import { APIContext } from "./APIContext";

const TEMP_SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b";
const TEMP_CHAR_UUID    = "beb5483e-36e1-4688-b7f5-ea07361b26a8";

export const BLEContext = createContext<any>({});

export function BLEProvider({ children }: { children: React.ReactNode }) {
  const manager = useRef(new BleManager()).current;
  const [connected, setConnected] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [temperature, setTemperature] = useState<number | null>(null);
  const deviceRef = useRef<Device | null>(null);
  const { postReading, patient } = useContext(APIContext);

  useEffect(() => {
    return () => { manager.destroy(); };
  }, []);

  const connect = async () => {
    setScanning(true);
    manager.startDeviceScan(null, { allowDuplicates: false }, async (err, device) => {
      if (err) { setScanning(false); return; }
      if (device?.name === "ThronomedICE") {
        manager.stopDeviceScan();
        try {
          const d = await device.connect();
          await d.discoverAllServicesAndCharacteristics();
          deviceRef.current = d;
          setConnected(true);
          setScanning(false);

          d.monitorCharacteristicForService(TEMP_SERVICE_UUID, TEMP_CHAR_UUID, (e, char) => {
            if (e || !char?.value) return;
            const json = JSON.parse(Buffer.from(char.value, "base64").toString("utf8"));
            const temp: number = json.temperature;
            setTemperature(temp);
            if (patient?.id) {
              postReading({ patient_id: patient.id, temperature: temp });
            }
          });
        } catch {
          setScanning(false);
        }
      }
    });
    setTimeout(() => { manager.stopDeviceScan(); setScanning(false); }, 15000);
  };

  const disconnect = async () => {
    await deviceRef.current?.cancelConnection();
    deviceRef.current = null;
    setConnected(false);
    setTemperature(null);
  };

  return (
    <BLEContext.Provider value={{ connected, scanning, temperature, connect, disconnect }}>
      {children}
    </BLEContext.Provider>
  );
}
