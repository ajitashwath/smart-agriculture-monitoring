from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.database import Alert, get_session
from cloud.ws_manager import ws_manager

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

class AlertCreatePayload(BaseModel):
    alert_type: str   # PEST | INTRUDER | NUTRIENT | SYSTEM | CAMERA
    severity: str = "WARNING"
    message: str
    zone_id: Optional[str] = None
    node_id: Optional[str] = None
    farm_id: str = "farm-001"


@router.post("/", status_code=201)
async def create_alert(
    payload: AlertCreatePayload,
    session: AsyncSession = Depends(get_session),
):
    alert = Alert(**payload.model_dump())
    session.add(alert)
    await session.commit()
    await session.refresh(alert)

    await ws_manager.broadcast_all({
        "type": "alert",
        "data": {
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "zone_id": alert.zone_id,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        },
    })
    return {"status": "created", "alert_id": alert.id}


@router.get("/")
async def list_alerts(
    unacknowledged_only: bool = True,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    q = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if unacknowledged_only:
        q = q.where(Alert.acknowledged == False)  # noqa: E712
    result = await session.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "alert_type": r.alert_type,
            "severity": r.severity,
            "message": r.message,
            "zone_id": r.zone_id,
            "node_id": r.node_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "acknowledged": r.acknowledged,
        }
        for r in rows
    ]


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    alert.acknowledged_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return {"status": "acknowledged", "alert_id": alert_id}
