from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text, func
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./sams.db")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(32), nullable=False, index=True)
    zone_id = Column(String(32), nullable=False, index=True)
    farm_id = Column(String(32), default="farm-001")
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    soil_moisture = Column(Float, nullable=False)
    temperature_c = Column(Float, nullable=False)
    humidity_pct = Column(Float, nullable=False)
    wind_speed_mps = Column(Float, default=0.0)
    battery_pct = Column(Float, default=100.0)
    pest_alert = Column(Boolean, default=False)
    camera_event = Column(Boolean, default=False)
    signal_rssi = Column(Integer, default=-60)


class IrrigationEvent(Base):
    __tablename__ = "irrigation_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(32), nullable=False, index=True)
    pump_id = Column(String(32), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    water_dispensed_litres = Column(Float, nullable=True)
    trigger_reason = Column(String(128), default="ML_DECISION")
    decision_confidence = Column(Float, nullable=True)
    is_manual = Column(Boolean, default=False)


class PumpLog(Base):
    __tablename__ = "pump_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pump_id = Column(String(32), nullable=False, index=True)
    zone_id = Column(String(32), nullable=False)
    event = Column(String(32), nullable=False)   # ON | OFF | ERROR | TIMEOUT
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    details = Column(Text, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    farm_id = Column(String(32), default="farm-001")
    zone_id = Column(String(32), nullable=True)
    node_id = Column(String(32), nullable=True)
    alert_type = Column(String(64), nullable=False)         # PEST | INTRUDER | NUTRIENT | SYSTEM | CAMERA
    severity = Column(String(16), default="WARNING")        # INFO | WARNING | CRITICAL
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
