from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.database import IrrigationEvent, SensorReading, Alert, get_session

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/reports/irrigation-summary")
async def irrigation_summary(
    days: int = 7,
    session: AsyncSession = Depends(get_session),
):
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(
            IrrigationEvent.zone_id,
            func.count(IrrigationEvent.id).label("events"),
            func.sum(IrrigationEvent.water_dispensed_litres).label("total_water"),
            func.sum(IrrigationEvent.duration_seconds).label("total_duration"),
        )
        .where(IrrigationEvent.started_at >= since)
        .group_by(IrrigationEvent.zone_id)
    )
    rows = result.all()
    return [
        {
            "zone_id": r.zone_id,
            "event_count": r.events,
            "total_water_litres": round(r.total_water or 0, 2),
            "total_duration_hours": round((r.total_duration or 0) / 3600, 2),
        }
        for r in rows
    ]


@router.get("/reports/crop-recommendations")
async def crop_recommendations():
    crops = [
        {
            "crop": "Tomato",
            "suitability_score": 0.91,
            "water_requirement": "Medium",
            "expected_yield_tons_ha": 22.5,
            "notes": "Ideal for current loamy soil and temperature profile.",
        },
        {
            "crop": "Chili Pepper",
            "suitability_score": 0.84,
            "water_requirement": "Low-Medium",
            "expected_yield_tons_ha": 12.0,
            "notes": "Well suited for well-drained loamy soil.",
        },
        {
            "crop": "Maize",
            "suitability_score": 0.76,
            "water_requirement": "High",
            "expected_yield_tons_ha": 5.8,
            "notes": "Consider only if irrigation capacity is adequate.",
        },
    ]
    return {"recommendations": crops, "generated_at": datetime.now(tz=timezone.utc).isoformat()}


@router.get("/reports/market-prices")
async def market_prices():
    base_prices = {
        "Tomato": 18.5,
        "Chili Pepper": 65.0,
        "Maize": 22.0,
        "Wheat": 24.5,
        "Rice": 32.0,
    }
    return {
        "prices": [
            {
                "crop": crop,
                "price_per_quintal_inr": round(
                    price * (1 + random.uniform(-0.05, 0.05)), 2
                ),
                "trend": random.choice(["UP", "DOWN", "STABLE"]),
                "market": "APMC Bangalore",
            }
            for crop, price in base_prices.items()
        ],
        "as_of": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/camera/events")
async def camera_events(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(SensorReading)
        .where(SensorReading.camera_event == True)
        .order_by(SensorReading.timestamp.desc())
        .limit(20)
    )
    rows = result.scalars().all()
    return [
        {
            "node_id": r.node_id,
            "zone_id": r.zone_id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "event": "MOTION_DETECTED",
        }
        for r in rows
    ]


@router.get("/system/status")
async def system_status(session: AsyncSession = Depends(get_session)):
    sensor_count = await session.scalar(
        select(func.count(SensorReading.id)).where(
            SensorReading.ingested_at >= datetime.now(tz=timezone.utc) - timedelta(minutes=10)
        )
    )
    open_alerts = await session.scalar(
        select(func.count(Alert.id)).where(Alert.acknowledged == False)  # noqa: E712
    )
    return {
        "status": "operational",
        "sensors_active_last_10min": sensor_count or 0,
        "open_alerts": open_alerts or 0,
        "checked_at": datetime.now(tz=timezone.utc).isoformat(),
    }
