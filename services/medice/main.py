from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List
import logging

from models import (
    Base, engine, get_db,
    Patient, Guardian, TempReading, FeverEvent,
    TempReadingIn, TempReadingOut, PatientCreate, GuardianCreate, FeverEventOut,
)
from fever_analyzer import FeverAnalyzer
from blockchain import BlockchainService
from notifications import NotificationService
from hospital_api import router as hospital_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

fever_analyzer       = FeverAnalyzer()
blockchain_service   = BlockchainService()
notification_service = NotificationService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("ThronomedICE service started | blockchain=%s",
                blockchain_service.is_connected)
    yield


app = FastAPI(
    title="ThronomedICE - Temperature Monitoring",
    description="IoT fever monitoring with blockchain-secured patient history",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(hospital_router)


# ---------------------------------------------------------------------------
# Core reading ingestion
# ---------------------------------------------------------------------------

@app.post("/readings", response_model=TempReadingOut)
async def submit_reading(
    reading: TempReadingIn,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Receive a temperature reading from the BLE gateway or mobile app."""
    patient = db.query(Patient).filter(Patient.device_id == reading.device_id).first()
    if not patient:
        raise HTTPException(404, f"No patient for device {reading.device_id}")

    ts       = reading.timestamp or datetime.utcnow()
    analysis = fever_analyzer.analyze(patient.id, reading.object_temp, ts)

    db_reading = TempReading(
        patient_id   = patient.id,
        device_id    = reading.device_id,
        object_temp  = reading.object_temp,
        ambient_temp = reading.ambient_temp,
        is_fever     = analysis["is_fever"],
        timestamp    = ts,
    )
    db.add(db_reading)

    # ---- fever lifecycle ----
    if analysis["is_new_fever"]:
        event = FeverEvent(
            patient_id    = patient.id,
            started_at    = ts,
            peak_temp     = reading.object_temp,
            readings_count = 1,
        )
        db.add(event)
        db.flush()   # get event.id
        fever_analyzer.register_fever_started(patient.id, event.id)

        bg.add_task(_handle_new_fever, patient, event, reading.object_temp,
                    analysis["fever_level"])

    elif analysis["is_fever"] and analysis["active_fever_id"]:
        ev = db.query(FeverEvent).filter(FeverEvent.id == analysis["active_fever_id"]).first()
        if ev:
            ev.readings_count += 1
            if reading.object_temp > ev.peak_temp:
                ev.peak_temp = reading.object_temp

    elif analysis["is_fever_ending"] and analysis["active_fever_id"]:
        ev = db.query(FeverEvent).filter(FeverEvent.id == analysis["active_fever_id"]).first()
        if ev:
            ev.ended_at = ts
        fever_analyzer.register_fever_ended(patient.id)
        if patient.guardian and patient.guardian.fcm_token:
            bg.add_task(notification_service.send_fever_ended,
                        patient.guardian.fcm_token, patient.name)

    if analysis["send_antipyretic_reminder"] and patient.guardian:
        bg.add_task(notification_service.send_antipyretic_reminder,
                    patient.guardian.fcm_token, patient.name, reading.object_temp)

    db.commit()
    db.refresh(db_reading)

    # record fever readings on-chain asynchronously
    if analysis["is_fever"]:
        bg.add_task(_record_on_chain, db_reading.id, patient.id,
                    reading.object_temp, ts)

    return db_reading


async def _handle_new_fever(patient, event, temp: float, level: str):
    if patient.guardian and patient.guardian.fcm_token:
        if level == "high_fever":
            await notification_service.send_high_fever_alert(
                patient.guardian.fcm_token, patient.name, temp)
        else:
            await notification_service.send_fever_alert(
                patient.guardian.fcm_token, patient.name, temp)

    tx = await blockchain_service.record_fever_event(patient.id, temp, datetime.utcnow())
    if tx:
        from models import SessionLocal
        with SessionLocal() as db:
            ev = db.query(FeverEvent).filter(FeverEvent.id == event.id).first()
            if ev:
                ev.blockchain_tx_hash = tx
                ev.notification_sent  = True
                db.commit()


async def _record_on_chain(reading_id: str, patient_id: str, temp: float, ts: datetime):
    tx = await blockchain_service.record_fever_event(patient_id, temp, ts)
    if tx:
        from models import SessionLocal
        with SessionLocal() as db:
            r = db.query(TempReading).filter(TempReading.id == reading_id).first()
            if r:
                r.blockchain_tx_hash = tx
                db.commit()


# ---------------------------------------------------------------------------
# Patient / Guardian management
# ---------------------------------------------------------------------------

@app.post("/guardians", status_code=201)
def create_guardian(g: GuardianCreate, db: Session = Depends(get_db)):
    row = Guardian(**g.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name}


@app.put("/guardians/{guardian_id}/fcm-token")
def update_fcm_token(guardian_id: str, fcm_token: str, db: Session = Depends(get_db)):
    row = db.query(Guardian).filter(Guardian.id == guardian_id).first()
    if not row:
        raise HTTPException(404, "Guardian not found")
    row.fcm_token = fcm_token
    db.commit()
    return {"status": "updated"}


@app.post("/patients", status_code=201)
def create_patient(p: PatientCreate, db: Session = Depends(get_db)):
    if not db.query(Guardian).filter(Guardian.id == p.guardian_id).first():
        raise HTTPException(404, "Guardian not found")
    row = Patient(**p.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "device_id": row.device_id}


# ---------------------------------------------------------------------------
# Fever history & status
# ---------------------------------------------------------------------------

@app.get("/patients/{patient_id}/fever-history", response_model=List[FeverEventOut])
def fever_history(patient_id: str, db: Session = Depends(get_db)):
    return (
        db.query(FeverEvent)
        .filter(FeverEvent.patient_id == patient_id)
        .order_by(FeverEvent.started_at.desc())
        .all()
    )


@app.get("/patients/{patient_id}/blockchain-history")
async def blockchain_history(patient_id: str):
    records = await blockchain_service.get_fever_history(patient_id)
    return {"patient_id": patient_id, "blockchain_records": records}


@app.get("/patients/{patient_id}/current-temp")
def current_temp(patient_id: str, db: Session = Depends(get_db)):
    r = (
        db.query(TempReading)
        .filter(TempReading.patient_id == patient_id)
        .order_by(TempReading.timestamp.desc())
        .first()
    )
    if not r:
        raise HTTPException(404, "No readings found")
    return {
        "patient_id":          patient_id,
        "current_temp":        r.object_temp,
        "is_fever":            r.is_fever,
        "last_reading":        r.timestamp.isoformat(),
        "has_active_fever":    patient_id in fever_analyzer.active_fever_patients,
    }


@app.put("/fever-events/{event_id}/antipyretic")
def record_antipyretic(event_id: str, db: Session = Depends(get_db)):
    """Call this when a parent confirms they gave antipyretic medication."""
    ev = db.query(FeverEvent).filter(FeverEvent.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Fever event not found")
    ev.antipyretic_given    = True
    ev.antipyretic_given_at = datetime.utcnow()
    db.commit()
    fever_analyzer.register_antipyretic_given(ev.patient_id, ev.antipyretic_given_at)
    return {"status": "recorded", "at": ev.antipyretic_given_at.isoformat()}


@app.get("/health")
def health():
    return {
        "status":                 "ok",
        "blockchain_connected":   blockchain_service.is_connected,
        "active_fever_patients":  len(fever_analyzer.active_fever_patients),
    }
