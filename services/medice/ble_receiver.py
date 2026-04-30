"""
BLE Gateway for Raspberry Pi or similar Linux-based gateway device.

Alternatively, the parent's mobile app (React Native) reads BLE directly
and POSTs to /readings - this module is for a fixed room gateway.
"""
import asyncio
import json
import logging
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

# Must match firmware config.h
TEMP_SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
TEMP_CHAR_UUID    = "beb5483e-36e1-4688-b7f5-ea07361b26a8"


class BLEGateway:
    """
    Scans for ThronomedICE chips and forwards readings to the monitoring API.
    Requires: pip install bleak
    """

    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url  = api_url
        self._running = False

    async def start(self):
        try:
            import bleak  # noqa: F401
        except ImportError:
            logger.warning("bleak not installed - BLE gateway unavailable")
            return

        self._running = True
        logger.info("BLE gateway started (API: %s)", self.api_url)
        await self._scan_loop()

    async def _scan_loop(self):
        from bleak import BleakScanner
        while self._running:
            devices = await BleakScanner.discover(timeout=5.0)
            for dev in devices:
                if dev.name and "ThronomedICE" in dev.name:
                    logger.info("Found chip: %s (%s)", dev.name, dev.address)
                    asyncio.create_task(self._stream(dev.address))
            await asyncio.sleep(30)

    async def _stream(self, address: str):
        from bleak import BleakClient
        try:
            async with BleakClient(address) as client:
                while self._running and client.is_connected:
                    raw = await client.read_gatt_char(TEMP_CHAR_UUID)
                    payload = json.loads(raw.decode())
                    await self._forward(payload)
                    await asyncio.sleep(10)
        except Exception as exc:
            logger.error("BLE stream error for %s: %s", address, exc)

    async def _forward(self, payload: dict):
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.api_url}/readings",
                    json={
                        "device_id":    payload["device_id"],
                        "object_temp":  payload["object_temp"],
                        "ambient_temp": payload["ambient_temp"],
                        "timestamp":    datetime.utcnow().isoformat(),
                    },
                    timeout=5.0,
                )
        except Exception as exc:
            logger.error("Forward failed: %s", exc)

    def stop(self):
        self._running = False
