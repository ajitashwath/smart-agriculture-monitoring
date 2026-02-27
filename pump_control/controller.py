from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("sams.pump_control")


class PumpState(str, Enum):
    OFF = "OFF"
    ON = "ON"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass
class PumpRunLog:
    pump_id: str
    zone_id: str
    started_at: str
    ended_at: Optional[str]
    duration_seconds: float
    water_dispensed_litres: float
    reason: str
    anomaly: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "pump_id": self.pump_id,
            "zone_id": self.zone_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": round(self.duration_seconds, 2),
            "water_dispensed_litres": round(self.water_dispensed_litres, 3),
            "reason": self.reason,
            "anomaly": self.anomaly,
        }


class PumpController:
    def __init__(
        self,
        pump_id: str,
        zone_id: str,
        capacity_lph: float = 1200.0,
        safety_timeout_seconds: int = 900,
    ) -> None:
        self.pump_id = pump_id
        self.zone_id = zone_id
        self._capacity_lph = capacity_lph
        self._safety_timeout = safety_timeout_seconds
        self._state = PumpState.OFF
        self._started_at: Optional[float] = None
        self._started_iso: Optional[str] = None
        self._target_duration: Optional[float] = None
        self._logs: List[PumpRunLog] = []
        self._task: Optional[asyncio.Task] = None

    @property
    def state(self) -> PumpState:
        return self._state

    @property
    def is_on(self) -> bool:
        return self._state == PumpState.ON

    def runtime_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.monotonic() - self._started_at

    def water_dispensed_litres(self) -> float:
        return (self.runtime_seconds() / 3600.0) * self._capacity_lph

    async def on(
        self,
        duration_minutes: int = 15,
        reason: str = "DECISION_ENGINE",
    ) -> bool:
        if self._state == PumpState.ON:
            logger.info(f"[{self.pump_id}] Already ON — idempotent no-op")
            return False

        duration_secs = min(duration_minutes * 60, self._safety_timeout)
        self._state = PumpState.ON
        self._started_at = time.monotonic()
        self._started_iso = datetime.now(tz=timezone.utc).isoformat()
        self._target_duration = duration_secs

        logger.info(
            f"[{self.pump_id}] ON → zone={self.zone_id} "
            f"duration={duration_minutes}min reason={reason}"
        )

        self._task = asyncio.create_task(
            self._auto_off(duration_secs, reason)
        )
        return True

    async def off(self, reason: str = "MANUAL_STOP") -> PumpRunLog:
        if self._state != PumpState.ON:
            logger.debug(f"[{self.pump_id}] Already OFF — no-op")
            return self._make_log(reason, anomaly=None)

        if self._task and not self._task.done():
            self._task.cancel()

        return self._finalise(reason, anomaly=None)

    async def _auto_off(self, duration_secs: float, reason: str) -> None:
        try:
            await asyncio.sleep(duration_secs)
            runtime = self.runtime_seconds()
            anomaly = None
            if runtime >= self._safety_timeout:
                anomaly = f"SAFETY_TIMEOUT after {runtime:.0f}s"
                self._state = PumpState.TIMEOUT
                logger.warning(f"[{self.pump_id}] Safety timeout triggered!")
            self._finalise(f"AUTO_OFF:{reason}", anomaly=anomaly)
        except asyncio.CancelledError:
            pass

    def _finalise(self, reason: str, anomaly: Optional[str]) -> PumpRunLog:
        duration = self.runtime_seconds()
        water = self.water_dispensed_litres()
        ended_iso = datetime.now(tz=timezone.utc).isoformat()
        self._state = PumpState.OFF
        log = PumpRunLog(
            pump_id=self.pump_id,
            zone_id=self.zone_id,
            started_at=self._started_iso or ended_iso,
            ended_at=ended_iso,
            duration_seconds=duration,
            water_dispensed_litres=water,
            reason=reason,
            anomaly=anomaly,
        )
        self._logs.append(log)
        self._started_at = None
        logger.info(
            f"[{self.pump_id}] OFF — "
            f"runtime={duration:.1f}s water={water:.2f}L reason={reason}"
        )
        return log

    def _make_log(self, reason: str, anomaly: Optional[str]) -> PumpRunLog:
        return PumpRunLog(
            pump_id=self.pump_id,
            zone_id=self.zone_id,
            started_at=self._started_iso or "",
            ended_at=None,
            duration_seconds=0.0,
            water_dispensed_litres=0.0,
            reason=reason,
            anomaly=anomaly,
        )

    def status(self) -> dict:
        return {
            "pump_id": self.pump_id,
            "zone_id": self.zone_id,
            "state": self._state.value,
            "runtime_seconds": round(self.runtime_seconds(), 1),
            "water_dispensed_litres": round(self.water_dispensed_litres(), 3),
            "target_duration_seconds": self._target_duration,
        }

    def history(self) -> List[dict]:
        return [log.to_dict() for log in self._logs[-20:]]


class PumpManager:
    def __init__(self) -> None:
        self._pumps: Dict[str, PumpController] = {}

    def register(self, pump: PumpController) -> None:
        self._pumps[pump.pump_id] = pump

    def get(self, pump_id: str) -> Optional[PumpController]:
        return self._pumps.get(pump_id)

    def all_status(self) -> List[dict]:
        return [p.status() for p in self._pumps.values()]
