from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.database import IrrigationEvent, PumpLog, get_session
from cloud.ws_manager import ws_manager

router = APIRouter(prefix="/api/v1/irrigation", tags=["irrigation"])

class IrrigationStartPayload(BaseModel):
    zone_id: str
    pump_id: str
    trigger_reason: str = "ML_DECISION"
    decision_confidence: float = 0.0
    is_manual: bool = False

class IrrigationEndPayload(BaseModel):
    zone_id: str
    pump_id: str
    duration_seconds: float
    water_dispensed_litres: float

@router.post("/start", status_code=202)
async def record_irrigation_start(
    payload: IrrigationStartPayload,
    session: AsyncSession = Depends(get_session),
):
    event = IrrigationEvent(
        zone_id=payload.zone_id,
        pump_id=payload.pump_id,
        started_at=datetime.now(tz=timezone.utc),
        trigger_reason=payload.trigger_reason,
        decision_confidence=payload.decision_confidence,
        is_manual=payload.is_manual,
    )
    session.add(event)
    pump_log = PumpLog(
        pump_id=payload.pump_id,
        zone_id=payload.zone_id,
        event="ON",
        details=f"reason={payload.trigger_reason}",
    )
    session.add(pump_log)
    await session.commit()
    await session.refresh(event)

    await ws_manager.broadcast_all({
        "type": "irrigation_event",
        "data": {
            "event": "started",
            "zone_id": payload.zone_id,
            "pump_id": payload.pump_id,
            "reason": payload.trigger_reason,
            "is_manual": payload.is_manual,
        },
    })
    return {"status": "recorded", "event_id": event.id}


@router.post("/end", status_code=202)
async def record_irrigation_end(
    payload: IrrigationEndPayload,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(IrrigationEvent)
        .where(IrrigationEvent.zone_id == payload.zone_id)
        .where(IrrigationEvent.ended_at == None)  # noqa: E711
        .order_by(IrrigationEvent.started_at.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()
    if event:
        event.ended_at = datetime.now(tz=timezone.utc)
        event.duration_seconds = payload.duration_seconds
        event.water_dispensed_litres = payload.water_dispensed_litres
        session.add(PumpLog(
            pump_id=payload.pump_id,
            zone_id=payload.zone_id,
            event="OFF",
            details=f"duration={payload.duration_seconds:.1f}s water={payload.water_dispensed_litres:.2f}L",
        ))
        await session.commit()

    await ws_manager.broadcast_all({
        "type": "irrigation_event",
        "data": {
            "event": "ended",
            "zone_id": payload.zone_id,
            "pump_id": payload.pump_id,
            "duration_seconds": payload.duration_seconds,
            "water_dispensed_litres": payload.water_dispensed_litres,
        },
    })
    return {"status": "recorded"}


@router.get("/history")
async def get_irrigation_history(
    zone_id: Optional[str] = None,
    days: int = 7,
    session: AsyncSession = Depends(get_session),
):
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    q = select(IrrigationEvent).where(IrrigationEvent.started_at >= since)
    if zone_id:
        q = q.where(IrrigationEvent.zone_id == zone_id)
    q = q.order_by(IrrigationEvent.started_at.desc()).limit(500)
    result = await session.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "zone_id": r.zone_id,
            "pump_id": r.pump_id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "duration_seconds": r.duration_seconds,
            "water_dispensed_litres": r.water_dispensed_litres,
            "trigger_reason": r.trigger_reason,
            "is_manual": r.is_manual,
        }
        for r in rows
    ]


@router.post("/manual-override")
async def manual_override(
    zone_id: str = Body(..., embed=True),
    action: str = Body(..., embed=True),
    duration_minutes: int = Body(default=15, embed=True),
):
    await ws_manager.broadcast_all({
        "type": "manual_override",
        "data": {
            "zone_id": zone_id,
            "action": action,
            "duration_minutes": duration_minutes,
        },
    })
    return {"status": "override_sent", "zone_id": zone_id, "action": action}
