import httpx
import os

FCM_URL     = "https://fcm.googleapis.com/fcm/send"
FCM_KEY     = os.getenv("FCM_SERVER_KEY", "")
_AUTH       = {"Authorization": f"key={FCM_KEY}", "Content-Type": "application/json"}

async def _send(token: str, title: str, body: str, data: dict = {}):
    if not token or not FCM_KEY:
        return
    payload = {"to": token, "notification": {"title": title, "body": body}, "data": data}
    async with httpx.AsyncClient() as c:
        await c.post(FCM_URL, headers=_AUTH, json=payload, timeout=10)

async def send_fever_alert(token: str, temp: float):
    await _send(token, "🌡️ Pyretós Anichthíke",
                f"Thermokrasia: {temp:.1f}°C", {"type": "fever", "temp": str(temp)})

async def send_high_fever_alert(token: str, temp: float):
    await _send(token, "⚠️ Ypsilon Pyretós!",
                f"Thermokrasia {temp:.1f}°C — Epikoinoníste me giatro!",
                {"type": "high_fever", "temp": str(temp)})

async def send_antipyretic_reminder(token: str):
    await _send(token, "💊 Antipy retikó ?",
                "Pérasan 4 óres apó to teleutaío antipyretikó.",
                {"type": "antipyretic_reminder"})

async def send_fever_ended(token: str):
    await _send(token, "✅ Pyretós Telíose",
                "I thermokrasia epéstrexe se kanoniká epípeda.",
                {"type": "fever_ended"})

async def send_spo2_alert(token: str, spo2: float, level: str):
    emoji = "🚨" if level == "critical" else "⚠️"
    await _send(token, f"{emoji} SpO2 {'KRITIKO' if level == 'critical' else 'Chamiló'}!",
                f"Methaneós aimatikós: {spo2:.0f}% — {'Epikoinoníste me giatro AMESA!' if level == 'critical' else 'Paratírisi apaitítai.'}",
                {"type": "spo2_alert", "spo2": str(spo2), "level": level})

async def send_hr_alert(token: str, bpm: int, level: str):
    label = "Bradykardia" if level == "bradycardia" else "Tachykardia"
    await _send(token, f"❤️‍🩹 {label}!",
                f"Kardiá : {bpm} BPM — Parakaló epikoinoniste me iatró.",
                {"type": "hr_alert", "bpm": str(bpm), "level": level})
