from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
import os

from models import get_db, Patient, FeverEvent, HospitalAccess, TempReading, FeverEventOut

router = APIRouter(prefix="/hospital", tags=["hospital"])

HOSPITAL_API_KEY = os.getenv("HOSPITAL_API_KEY", "")


def _verify_key(x_hospital_key: str = Header(...)):
    if not HOSPITAL_API_KEY or x_hospital_key != HOSPITAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid hospital API key")
    return x_hospital_key


def _has_access(patient_id: str, hospital_id: str, db: Session) -> bool:
    return db.query(HospitalAccess).filter(
        HospitalAccess.patient_id  == patient_id,
        HospitalAccess.hospital_id == hospital_id,
        HospitalAccess.is_active   == True,
    ).first() is not None


@router.post("/patients/{patient_id}/access")
def grant_access(
    patient_id:           str,
    hospital_id:          str,
    hospital_name:        str,
    guardian_confirmation: bool,
    db: Session = Depends(get_db),
    _: str = Depends(_verify_key),
):
    if not guardian_confirmation:
        raise HTTPException(status_code=400, detail="Guardian must confirm access")
    if not db.query(Patient).filter(Patient.id == patient_id).first():
        raise HTTPException(status_code=404, detail="Patient not found")

    row = db.query(HospitalAccess).filter(
        HospitalAccess.patient_id  == patient_id,
        HospitalAccess.hospital_id == hospital_id,
    ).first()
    if row:
        row.is_active  = True
        row.revoked_at = None
    else:
        db.add(HospitalAccess(patient_id=patient_id,
                              hospital_id=hospital_id,
                              hospital_name=hospital_name))
    db.commit()
    return {"status": "access_granted", "patient_id": patient_id, "hospital_id": hospital_id}


@router.delete("/patients/{patient_id}/access")
def revoke_access(
    patient_id:  str,
    hospital_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(_verify_key),
):
    row = db.query(HospitalAccess).filter(
        HospitalAccess.patient_id  == patient_id,
        HospitalAccess.hospital_id == hospital_id,
        HospitalAccess.is_active   == True,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="No active access found")
    row.is_active  = False
    row.revoked_at = datetime.utcnow()
    db.commit()
    return {"status": "access_revoked"}


@router.get("/patients/{patient_id}/fever-history")
def fever_history(
    patient_id:  str,
    hospital_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(_verify_key),
):
    if not _has_access(patient_id, hospital_id, db):
        raise HTTPException(status_code=403, detail="No access to this patient")

    events = (
        db.query(FeverEvent)
        .filter(FeverEvent.patient_id == patient_id)
        .order_by(FeverEvent.started_at.desc())
        .all()
    )
    return {
        "patient_id": patient_id,
        "total_fever_events": len(events),
        "events": [FeverEventOut.model_validate(e) for e in events],
    }


@router.get("/patients/{patient_id}/recent-readings")
def recent_readings(
    patient_id:  str,
    hospital_id: str,
    hours:       int = 24,
    db: Session = Depends(get_db),
    _: str = Depends(_verify_key),
):
    if not _has_access(patient_id, hospital_id, db):
        raise HTTPException(status_code=403, detail="No access to this patient")

    cutoff   = datetime.utcnow() - timedelta(hours=hours)
    readings = (
        db.query(TempReading)
        .filter(TempReading.patient_id == patient_id,
                TempReading.timestamp  >= cutoff)
        .order_by(TempReading.timestamp.desc())
        .all()
    )
    return {
        "patient_id":      patient_id,
        "hours":           hours,
        "readings_count":  len(readings),
        "readings": [
            {
                "temp":           r.object_temp,
                "is_fever":       r.is_fever,
                "timestamp":      r.timestamp.isoformat(),
                "blockchain_tx":  r.blockchain_tx_hash,
            }
            for r in readings
        ],
    }
