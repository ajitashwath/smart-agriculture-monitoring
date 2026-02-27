from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func

from cloud.database import SensorReading, get_session
from cloud.ws_manager import ws_manager

router = APIRouter(prefix="/api/v1/sensors", tags=["sensors"])

class SensorIngestPayload(BaseModel):
    node_id: str
    zone_id: str
    timestamp: str
    soil_moisture: float
    temperature_c: float
    humidity_pct: float
    wind_speed_mps: float = 0.0
    battery_pct: float = 100.0
    pest_alert: bool = False
    camera_event: bool = False
    signal_rssi: int = -60
    farm_id: str = "farm-001"


@router.post("/ingest", status_code=202)
async def ingest_sensor_reading(
    payload: SensorIngestPayload,
    session: AsyncSession = Depends(get_session),
):
    try:
        ts = datetime.fromisoformat(payload.timestamp.replace("Z", "+00:00"))
    except ValueError:
        ts = datetime.now(tz=timezone.utc)

    record = SensorReading(
        node_id=payload.node_id,
        zone_id=payload.zone_id,
        farm_id=payload.farm_id,
        timestamp=ts,
        soil_moisture=payload.soil_moisture,
        temperature_c=payload.temperature_c,
        humidity_pct=payload.humidity_pct,
        wind_speed_mps=payload.wind_speed_mps,
        battery_pct=payload.battery_pct,
        pest_alert=payload.pest_alert,
        camera_event=payload.camera_event,
        signal_rssi=payload.signal_rssi,
    )
    session.add(record)
    await session.commit()

    await ws_manager.broadcast_all({
        "type": "sensor_reading",
        "data": payload.model_dump(),
    })

    return {"status": "accepted", "node_id": payload.node_id}


@router.get("/latest")
async def get_latest_readings(
    farm_id: str = "farm-001",
    session: AsyncSession = Depends(get_session),
):
    subq = (
        select(SensorReading.node_id, func.max(SensorReading.timestamp).label("max_ts"))
        .where(SensorReading.farm_id == farm_id)
        .group_by(SensorReading.node_id)
        .subquery()
    )
    result = await session.execute(
        select(SensorReading).join(
            subq,
            (SensorReading.node_id == subq.c.node_id) &
            (SensorReading.timestamp == subq.c.max_ts),
        )
    )
    rows = result.scalars().all()
    return [
        {
            "node_id": r.node_id,
            "zone_id": r.zone_id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "soil_moisture": r.soil_moisture,
            "temperature_c": r.temperature_c,
            "humidity_pct": r.humidity_pct,
            "wind_speed_mps": r.wind_speed_mps,
            "battery_pct": r.battery_pct,
            "pest_alert": r.pest_alert,
            "camera_event": r.camera_event,
        }
        for r in rows
    ]


@router.get("/history/{node_id}")
async def get_node_history(
    node_id: str,
    hours: int = Query(default=24, ge=1, le=168),
    session: AsyncSession = Depends(get_session),
):
    since = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    result = await session.execute(
        select(SensorReading)
        .where(SensorReading.node_id == node_id)
        .where(SensorReading.timestamp >= since)
        .order_by(SensorReading.timestamp.asc())
        .limit(2000)
    )
    rows = result.scalars().all()
    return [
        {
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "soil_moisture": r.soil_moisture,
            "temperature_c": r.temperature_c,
            "humidity_pct": r.humidity_pct,
        }
        for r in rows
    ]
