from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Dict, Optional

import httpx

from decision_engine.engine import DecisionEngine, ZoneState
from decision_engine.water_check import is_water_required
from pump_control.controller import PumpController, PumpManager

logger = logging.getLogger("sams.scheduler")

CYCLE_DELAY = int(os.getenv("CYCLE_DELAY_SECONDS", "30"))
CLOUD_URL = os.getenv("CLOUD_API_URL", "http://localhost:8000")


class SchedulerState(Enum):
    IDLE = auto()
    EVALUATING = auto()
    IRRIGATING = auto()
    COOLING_DOWN = auto()


class ZoneScheduler:
    def __init__(
        self,
        zone_id: str,
        pump: PumpController,
        engine: DecisionEngine,
        moisture_threshold: float = 0.30,
    ) -> None:
        self.zone_id = zone_id
        self._pump = pump
        self._engine = engine
        self._threshold = moisture_threshold
        self._state = SchedulerState.IDLE
        self._last_reading: Optional[ZoneState] = None

    def feed_reading(self, reading: dict) -> None:
        self._last_reading = ZoneState(
            zone_id=self.zone_id,
            moisture=reading.get("soil_moisture", 0.3),
            temperature_c=reading.get("temperature_c", 28.0),
            humidity_pct=reading.get("humidity_pct", 60.0),
            wind_speed_mps=reading.get("wind_speed_mps", 2.0),
            rain_probability=reading.get("rain_probability", 0.0),
            moisture_threshold=self._threshold,
        )

    async def evaluate(self, http: httpx.AsyncClient) -> None:
        if self._state != SchedulerState.IDLE:
            logger.debug(f"[{self.zone_id}] Skip (state={self._state.name})")
            return

        if self._last_reading is None:
            logger.debug(f"[{self.zone_id}] No reading yet — waiting")
            return

        self._state = SchedulerState.EVALUATING

        try:
            result = is_water_required(self._last_reading, engine=self._engine)
            logger.info(
                f"[{self.zone_id}] Decision: required={result.is_required} "
                f"urgency={result.urgency} confidence={result.confidence:.0%}"
            )

            try:
                await http.post(
                    f"{CLOUD_URL}/api/v1/irrigation/start"
                    if result.is_required else
                    f"{CLOUD_URL}/api/v1/alerts/",
                    json={
                        "zone_id": self.zone_id,
                        "pump_id": self._pump.pump_id,
                        "trigger_reason": result.guard_triggered or "ML_DECISION",
                        "decision_confidence": result.confidence,
                        "is_manual": False,
                    } if result.is_required else {
                        "alert_type": "SYSTEM",
                        "severity": "INFO",
                        "message": result.reason,
                        "zone_id": self.zone_id,
                    },
                    timeout=5.0,
                )
            except Exception as e:
                logger.warning(f"Cloud notify failed: {e}")

            if result.is_required:
                self._state = SchedulerState.IRRIGATING
                self._engine.record_irrigation(self.zone_id)
                await self._pump.on(
                    duration_minutes=result.recommended_duration_minutes,
                    reason=result.reason,
                )
                await asyncio.sleep(result.recommended_duration_minutes * 60)
                pump_log = await self._pump.off("SCHEDULER_CYCLE_COMPLETE")

                try:
                    await http.post(
                        f"{CLOUD_URL}/api/v1/irrigation/end",
                        json={
                            "zone_id": self.zone_id,
                            "pump_id": self._pump.pump_id,
                            "duration_seconds": pump_log.duration_seconds,
                            "water_dispensed_litres": pump_log.water_dispensed_litres,
                        },
                        timeout=5.0,
                    )
                except Exception as e:
                    logger.warning(f"Cloud end-notify failed: {e}")

                self._state = SchedulerState.COOLING_DOWN
                await asyncio.sleep(min(CYCLE_DELAY * 2, 120))
            else:
                self._state = SchedulerState.COOLING_DOWN
                await asyncio.sleep(CYCLE_DELAY)

        except Exception as exc:
            logger.exception(f"[{self.zone_id}] Scheduler error: {exc}")
        finally:
            self._state = SchedulerState.IDLE


class IrrigationScheduler:
    def __init__(self, cycle_delay: int = CYCLE_DELAY) -> None:
        self._cycle_delay = cycle_delay
        self._zones: Dict[str, ZoneScheduler] = {}
        self._pump_mgr = PumpManager()
        self._engine = DecisionEngine()
        self._running = False

    def register_zone(
        self,
        zone_id: str,
        pump_id: str,
        capacity_lph: float = 1200.0,
        moisture_threshold: float = 0.30,
        safety_timeout: int = 900,
    ) -> None:
        pump = PumpController(
            pump_id=pump_id,
            zone_id=zone_id,
            capacity_lph=capacity_lph,
            safety_timeout_seconds=safety_timeout,
        )
        self._pump_mgr.register(pump)
        self._zones[zone_id] = ZoneScheduler(
            zone_id=zone_id,
            pump=pump,
            engine=self._engine,
            moisture_threshold=moisture_threshold,
        )
        logger.info(f"Registered zone={zone_id} pump={pump_id}")

    def feed_sensor_data(self, zone_id: str, reading: dict) -> None:
        if zone_id in self._zones:
            self._zones[zone_id].feed_reading(reading)

    def pump_status(self) -> list:
        return self._pump_mgr.all_status()

    async def run_forever(self) -> None:
        self._running = True
        logger.info(f"Scheduler running — cycle_delay={self._cycle_delay}s")
        async with httpx.AsyncClient(timeout=10.0) as http:
            while self._running:
                tasks = [
                    zone.evaluate(http) for zone in self._zones.values()
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(self._cycle_delay)

    def stop(self) -> None:
        self._running = False
