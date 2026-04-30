import httpx
import logging
import os

logger = logging.getLogger(__name__)

FCM_URL        = "https://fcm.googleapis.com/fcm/send"
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "")


class NotificationService:
    def __init__(self):
        self._key = FCM_SERVER_KEY

    async def send_fever_alert(self, token: str, patient_name: str, temp: float) -> bool:
        return await self._send(
            token,
            title=f"PYRETOS - {patient_name}",
            body=f"Thermokrasia: {temp:.1f}°C. Parakaloumeelegxte to paidi sas.",
            data={"type": "FEVER_ALERT", "temperature": str(temp)},
        )

    async def send_antipyretic_reminder(self, token: str, patient_name: str, temp: float) -> bool:
        return await self._send(
            token,
            title=f"Ypenthumisi Antipiretikoy - {patient_name}",
            body=f"Thermokrasia {temp:.1f}°C. Skefteite na dosete antipyretiko.",
            data={"type": "ANTIPYRETIC_REMINDER", "temperature": str(temp)},
        )

    async def send_high_fever_alert(self, token: str, patient_name: str, temp: float) -> bool:
        return await self._send(
            token,
            title=f"UYPSLOS PYRETOS - {patient_name}",
            body=f"Upselos pyrethos {temp:.1f}°C. Epikoinoniste me giatro.",
            data={"type": "HIGH_FEVER_ALERT", "temperature": str(temp), "urgent": "true"},
        )

    async def send_fever_ended(self, token: str, patient_name: str) -> bool:
        return await self._send(
            token,
            title=f"O pyretos ypochoriose - {patient_name}",
            body="I thermokrasia epestrepse se physiologika epipeda.",
            data={"type": "FEVER_ENDED"},
        )

    async def _send(self, token: str, title: str, body: str, data: dict) -> bool:
        if not self._key or not token:
            logger.warning("FCM key or token missing - skipping notification")
            return False

        payload = {
            "to": token,
            "notification": {"title": title, "body": body, "sound": "default"},
            "data": data,
            "priority": "high",
        }
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    FCM_URL,
                    json=payload,
                    headers={
                        "Authorization": f"key={self._key}",
                        "Content-Type": "application/json",
                    },
                    timeout=10.0,
                )
                if r.status_code == 200 and r.json().get("success") == 1:
                    logger.info("Notification sent: %s", title)
                    return True
                logger.error("FCM error %s: %s", r.status_code, r.text)
                return False
        except Exception as exc:
            logger.error("Notification failed: %s", exc)
            return False
