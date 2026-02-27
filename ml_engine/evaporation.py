from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class EvaporationResult:
    et0_mm_day: float
    penman_mm_day: float
    vapor_pressure_deficit: float
    temperature_c: float
    humidity_pct: float
    wind_speed_mps: float

    def to_dict(self) -> dict:
        return {
            "et0_mm_day": round(self.et0_mm_day, 3),
            "penman_mm_day": round(self.penman_mm_day, 3),
            "vapor_pressure_deficit_kpa": round(self.vapor_pressure_deficit, 3),
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "wind_speed_mps": self.wind_speed_mps,
        }


def _saturation_vapor_pressure(temp_c: float) -> float:
    return 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))


def _actual_vapor_pressure(temp_c: float, rh_pct: float) -> float:
    return _saturation_vapor_pressure(temp_c) * (rh_pct / 100.0)


def compute_evaporation_rate(
    temperature_c: float,
    humidity_pct: float,
    wind_speed_mps: float,
    temp_min_c: Optional[float] = None,
    temp_max_c: Optional[float] = None,
    elevation_m: float = 843.0,
    latitude_deg: float = 13.34,
    day_of_year: int = 180,
) -> EvaporationResult:
    es = _saturation_vapor_pressure(temperature_c)
    ea = _actual_vapor_pressure(temperature_c, humidity_pct)
    vpd = max(0.0, es - ea)

    lat_rad = math.radians(latitude_deg)
    dr = 1.0 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    ws_angle = math.acos(-math.tan(lat_rad) * math.tan(delta))
    Gsc = 0.0820
    Ra = (24.0 * 60.0 / math.pi) * Gsc * dr * (
        ws_angle * math.sin(lat_rad) * math.sin(delta)
        + math.cos(lat_rad) * math.cos(delta) * math.sin(ws_angle)
    )

    if temp_min_c is not None and temp_max_c is not None:
        td = max(0.0, temp_max_c - temp_min_c)
        et0_hs = 0.0023 * (temperature_c + 17.8) * math.sqrt(td) * Ra * 0.408
    else:
        td = max(2.0, (1.0 - humidity_pct / 100.0) * 25.0)
        et0_hs = 0.0023 * (temperature_c + 17.8) * math.sqrt(td) * Ra * 0.408

    u2 = max(0.5, wind_speed_mps)
    wind_factor = 1.0 + 0.12 * u2 / 2.0
    penman = et0_hs * wind_factor

    return EvaporationResult(
        et0_mm_day=max(0.0, round(et0_hs, 3)),
        penman_mm_day=max(0.0, round(penman, 3)),
        vapor_pressure_deficit=round(vpd, 4),
        temperature_c=temperature_c,
        humidity_pct=humidity_pct,
        wind_speed_mps=wind_speed_mps,
    )
