from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("sams.cloud.weather")

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
WEATHER_CITY = os.getenv("WEATHER_CITY", "Bengaluru")
WEATHER_MODE = os.getenv("WEATHER_MODE", "mock")
CACHE_TTL = int(os.getenv("WEATHER_CACHE_TTL", "1800"))
OWM_BASE = "https://api.openweathermap.org/data/2.5"
MAX_RETRIES = 3
TIMEOUT = 8.0

@dataclass
class WeatherForecast:
    timestamp: str
    city: str
    temperature_c: float
    feels_like_c: float
    humidity_pct: float
    wind_speed_mps: float
    rain_probability: float       # 0.0–1.0
    condition: str                # "Clear" | "Rain" | "Clouds" 
    source: str                   # "mock" | "live"


class WeatherService:
    def __init__(self) -> None:
        self._cache: Optional[WeatherForecast] = None
        self._cache_expires: float = 0.0
        self._lock = asyncio.Lock()

    def _generate_mock(self) -> WeatherForecast:
        now_hour = datetime.now().hour
        base_temp = 26.0 + 8.0 * (1 if 10 <= now_hour <= 16 else -0.5)
        temp = base_temp + random.gauss(0, 2.0)
        humidity = max(30.0, min(95.0, 70.0 - (temp - 26) * 1.5 + random.gauss(0, 5)))
        rain_prob = random.choices([0.0, 0.2, 0.5, 0.8], weights=[50, 25, 15, 10])[0]
        conditions = {0.0: "Clear", 0.2: "Partly Cloudy", 0.5: "Clouds", 0.8: "Rain"}
        condition = conditions.get(rain_prob, "Clear")
        return WeatherForecast(
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            city=WEATHER_CITY,
            temperature_c=round(temp, 1),
            feels_like_c=round(temp - 2.0, 1),
            humidity_pct=round(humidity, 1),
            wind_speed_mps=round(random.uniform(0.5, 6.0), 1),
            rain_probability=rain_prob,
            condition=condition,
            source="mock",
        )

    async def _fetch_live(self) -> WeatherForecast:
        if not WEATHER_API_KEY:
            raise ValueError("WEATHER_API_KEY is not set for live mode")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = await client.get(
                        f"{OWM_BASE}/weather",
                        params={"q": WEATHER_CITY, "appid": WEATHER_API_KEY, "units": "metric"},
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    fc_resp = await client.get(
                        f"{OWM_BASE}/forecast",
                        params={"q": WEATHER_CITY, "appid": WEATHER_API_KEY, "units": "metric", "cnt": 1},
                    )
                    fc_resp.raise_for_status()
                    fc_data = fc_resp.json()
                    rain_prob = fc_data["list"][0].get("pop", 0.0)

                    return WeatherForecast(
                        timestamp=datetime.now(tz=timezone.utc).isoformat(),
                        city=WEATHER_CITY,
                        temperature_c=data["main"]["temp"],
                        feels_like_c=data["main"]["feels_like"],
                        humidity_pct=data["main"]["humidity"],
                        wind_speed_mps=data["wind"]["speed"],
                        rain_probability=rain_prob,
                        condition=data["weather"][0]["main"],
                        source="live",
                    )
                except (httpx.HTTPError, KeyError) as exc:
                    logger.warning(f"Weather API error (attempt {attempt}): {exc}")
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"Weather API failed after {MAX_RETRIES} retries")

    async def get_forecast(self) -> WeatherForecast:
        async with self._lock:
            now = time.monotonic()
            if self._cache and now < self._cache_expires:
                logger.debug("Returning cached weather forecast")
                return self._cache

            if WEATHER_MODE == "mock" or not WEATHER_API_KEY:
                forecast = self._generate_mock()
            else:
                try:
                    forecast = await self._fetch_live()
                except Exception as exc:
                    logger.error(f"Live weather fetch failed, using mock: {exc}")
                    forecast = self._generate_mock()

            self._cache = forecast
            self._cache_expires = now + CACHE_TTL
            logger.info(f"Weather updated: {forecast.condition} "
                        f"rain={forecast.rain_probability:.0%} "
                        f"temp={forecast.temperature_c}°C")
            return forecast

    def to_dict(self, forecast: WeatherForecast) -> Dict[str, Any]:
        return asdict(forecast)

weather_service = WeatherService()
