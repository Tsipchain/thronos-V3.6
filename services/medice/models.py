from sqlalchemy import (
    create_engine, Column, String, Float, DateTime,
    Boolean, Integer, ForeignKey, Text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import os
import uuid

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./medice.db")
_connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Guardian(Base):
    __tablename__ = "guardians"
    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name       = Column(String, nullable=False)
    phone      = Column(String)
    email      = Column(String)
    fcm_token  = Column(String)          # Firebase Cloud Messaging push token
    wallet_address = Column(String)      # Thronos wallet
    created_at = Column(DateTime, default=datetime.utcnow)

    patients = relationship("Patient", back_populates="guardian")


class Patient(Base):
    __tablename__ = "patients"
    id                  = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name                = Column(String, nullable=False)
    birth_date          = Column(DateTime)
    device_id           = Column(String, unique=True)  # chip DEVICE_ID from firmware
    guardian_id         = Column(String, ForeignKey("guardians.id"))
    blockchain_address  = Column(String)
    created_at          = Column(DateTime, default=datetime.utcnow)

    guardian     = relationship("Guardian", back_populates="patients")
    readings     = relationship("TempReading", back_populates="patient")
    fever_events = relationship("FeverEvent",  back_populates="patient")


class TempReading(Base):
    __tablename__ = "temp_readings"
    id               = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id       = Column(String, ForeignKey("patients.id"))
    device_id        = Column(String)
    object_temp      = Column(Float)   # measured body temperature
    ambient_temp     = Column(Float)
    is_fever         = Column(Boolean, default=False)
    timestamp        = Column(DateTime, default=datetime.utcnow)
    blockchain_tx_hash = Column(String)

    patient = relationship("Patient", back_populates="readings")


class FeverEvent(Base):
    __tablename__ = "fever_events"
    id                   = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id           = Column(String, ForeignKey("patients.id"))
    started_at           = Column(DateTime)
    ended_at             = Column(DateTime, nullable=True)
    peak_temp            = Column(Float)
    readings_count       = Column(Integer, default=0)
    antipyretic_given    = Column(Boolean, default=False)
    antipyretic_given_at = Column(DateTime, nullable=True)
    notification_sent    = Column(Boolean, default=False)
    blockchain_tx_hash   = Column(String)
    hospital_notified    = Column(Boolean, default=False)
    notes                = Column(Text, nullable=True)

    patient = relationship("Patient", back_populates="fever_events")


class HospitalAccess(Base):
    __tablename__ = "hospital_access"
    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id    = Column(String, ForeignKey("patients.id"))
    hospital_id   = Column(String)
    hospital_name = Column(String)
    granted_at    = Column(DateTime, default=datetime.utcnow)
    revoked_at    = Column(DateTime, nullable=True)
    is_active     = Column(Boolean, default=True)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class TempReadingIn(BaseModel):
    device_id:    str
    object_temp:  float
    ambient_temp: float
    timestamp:    Optional[datetime] = None


class TempReadingOut(BaseModel):
    id:                  str
    patient_id:          str
    object_temp:         float
    ambient_temp:        float
    is_fever:            bool
    timestamp:           datetime
    blockchain_tx_hash:  Optional[str] = None

    class Config:
        from_attributes = True


class PatientCreate(BaseModel):
    name:        str
    birth_date:  Optional[datetime] = None
    device_id:   str
    guardian_id: str


class GuardianCreate(BaseModel):
    name:           str
    phone:          Optional[str] = None
    email:          Optional[str] = None
    fcm_token:      str
    wallet_address: Optional[str] = None


class FeverEventOut(BaseModel):
    id:                  str
    patient_id:          str
    started_at:          datetime
    ended_at:            Optional[datetime] = None
    peak_temp:           float
    readings_count:      int
    antipyretic_given:   bool
    antipyretic_given_at: Optional[datetime] = None
    blockchain_tx_hash:  Optional[str] = None

    class Config:
        from_attributes = True
