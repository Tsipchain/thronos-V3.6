from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from datetime import datetime
import aioredis
import os

from models import (
    Base, Guardian, Patient, TempReading, FeverEvent,
    TempReadingIn, TempReadingOut, PatientCreate, GuardianCreate, FeverEventOut,
)
from vital_analyzer import VitalAnalyzer
from notifications import (
    send_fever_alert, send_high_fever_alert,
    send_antipyretic_reminder, send_fever_ended,
    send_spo2_alert, send_hr_alert,
)
from blockchain import record_fever_start, record_fever_end, get_fever_history
from hospital_api import router as hospital_router
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_URL = os.getenv("DATABASE_URL", "postgresql://medice:medice@localhost/medice")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)

analyzer: VitalAnalyzer = None  # initialized in lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    global analyzer
    redis = await aioredis.from_url(REDIS_URL, decode_responses=False)
    analyzer = VitalAnalyzer(redis)
    Base.metadata.create_all(engine)
    yield
    await redis.close()

app = FastAPI(title="ThronomedICE Vital Signs API", version="2.0", lifespan=lifespan)
app.include_router(hospital_router)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/readings", response_model=dict)
async def post_reading(reading: TempReadingIn, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == int(reading.patient_id)).first()
    if not patient:
        raise HTTPException(404, "Patient not found")

    ts = reading.timestamp or datetime.utcnow()

    # Persist reading with SpO2 + BPM
    db_reading = TempReading(
        patient_id  = patient.id,
        device_id   = reading.device_id,
        temperature = reading.temperature,
        spo2        = reading.spo2,
        bpm         = reading.bpm,
        spo2_valid  = reading.spo2_valid or False,
        bpm_valid   = reading.bpm_valid  or False,
        timestamp   = ts,
    )
    db.add(db_reading)
    db.commit()

    # Analyze temperature
    t_result = await analyzer.analyze_temp(reading.patient_id, reading.temperature, ts)

    # Analyze SpO2 + BPM
    v_result = await analyzer.analyze_vitals(
        reading.patient_id,
        reading.spo2, reading.spo2_valid or False,
        reading.bpm,  reading.bpm_valid  or False,
    )

    fcm_token = patient.guardian.fcm_token if patient.guardian else None

    # ── Fever notifications ─────────────────────────────────────────────────
    if t_result["send_fever_alert"] and fcm_token:
        if t_result["fever_level"] == "high_fever":
            await send_high_fever_alert(fcm_token, reading.temperature)
        else:
            await send_fever_alert(fcm_token, reading.temperature)

    if t_result["send_antipyretic_reminder"] and fcm_token:
        await send_antipyretic_reminder(fcm_token)

    # ── New fever: create DB event + on-chain record ────────────────────────
    if t_result["is_new_fever"]:
        event = FeverEvent(
            patient_id = patient.id,
            start_time = ts,
            peak_temp  = reading.temperature,
        )
        db.add(event)
        db.commit()
        tx = await record_fever_start(str(patient.id), int(reading.temperature * 100), int(ts.timestamp()))
        event.blockchain_tx = tx
        db.commit()
        await analyzer.register_fever_started(reading.patient_id, str(event.id))

    # ── Fever peak update ───────────────────────────────────────────────────
    if t_result["active_fever_id"]:
        event = db.query(FeverEvent).filter(
            FeverEvent.id == int(t_result["active_fever_id"])
        ).first()
        if event:
            if reading.temperature > event.peak_temp:
                event.peak_temp = reading.temperature
                db.commit()

    # ── Fever ended ─────────────────────────────────────────────────────────
    if t_result["is_fever_ending"] and t_result["active_fever_id"]:
        event = db.query(FeverEvent).filter(
            FeverEvent.id == int(t_result["active_fever_id"])
        ).first()
        if event:
            vitals = await analyzer.get_fever_vitals(reading.patient_id)
            event.end_time  = ts
            event.min_spo2  = vitals["min_spo2"]
            event.avg_bpm   = vitals["avg_bpm"]
            db.commit()
            await record_fever_end(str(patient.id), event.id)
            if fcm_token:
                await send_fever_ended(fcm_token)

    # ── SpO2 / HR alerts ────────────────────────────────────────────────────
    if v_result["spo2_alert"] and fcm_token and reading.spo2:
        await send_spo2_alert(fcm_token, reading.spo2, v_result["spo2_level"])

    if v_result["hr_alert"] and fcm_token and reading.bpm:
        await send_hr_alert(fcm_token, reading.bpm, v_result["hr_level"])

    return {
        "status":           "ok",
        "fever_level":      t_result["fever_level"],
        "spo2_level":       v_result["spo2_level"],
        "hr_level":         v_result["hr_level"],
        "active_fever_id":  t_result["active_fever_id"],
        "is_new_fever":     t_result["is_new_fever"],
    }


@app.get("/patients/{patient_id}/vitals")
async def current_vitals(patient_id: int, db: Session = Depends(get_db)):
    reading = (
        db.query(TempReading)
        .filter(TempReading.patient_id == patient_id)
        .order_by(TempReading.timestamp.desc())
        .first()
    )
    if not reading:
        raise HTTPException(404, "No readings yet")
    return {
        "temperature": reading.temperature,
        "spo2":        reading.spo2,
        "bpm":         reading.bpm,
        "spo2_valid":  reading.spo2_valid,
        "bpm_valid":   reading.bpm_valid,
        "timestamp":   reading.timestamp,
    }


@app.get("/patients/{patient_id}/fever-history", response_model=list[FeverEventOut])
def fever_history(patient_id: int, db: Session = Depends(get_db)):
    return db.query(FeverEvent).filter(FeverEvent.patient_id == patient_id)\
             .order_by(FeverEvent.start_time.desc()).all()


@app.put("/fever-events/{event_id}/antipyretic")
async def mark_antipyretic(event_id: int, db: Session = Depends(get_db)):
    event = db.query(FeverEvent).filter(FeverEvent.id == event_id).first()
    if not event:
        raise HTTPException(404)
    event.antipyretic_given = True
    db.commit()
    await analyzer.register_antipyretic_given(str(event.patient_id), datetime.utcnow())
    return {"status": "ok"}


@app.post("/guardians", response_model=dict)
def create_guardian(g: GuardianCreate, db: Session = Depends(get_db)):
    guardian = Guardian(name=g.name, email=g.email)
    db.add(guardian)
    db.commit()
    return {"id": guardian.id}


@app.post("/patients", response_model=dict)
def create_patient(p: PatientCreate, db: Session = Depends(get_db)):
    patient = Patient(name=p.name, birth_date=p.birth_date, guardian_id=p.guardian_id)
    db.add(patient)
    db.commit()
    return {"id": patient.id}


@app.post("/patients/{patient_id}/fcm-token")
async def register_fcm(patient_id: int, body: dict, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient or not patient.guardian:
        raise HTTPException(404)
    patient.guardian.fcm_token = body.get("token")
    db.commit()
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0"}
