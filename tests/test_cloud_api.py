import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_sams.db"
os.environ["WEATHER_MODE"] = "mock"

from cloud.main import app
from cloud.database import init_db


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="module")
async def client():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ingest_sensor(client):
    payload = {
        "node_id": "node-TEST",
        "zone_id": "zone-1",
        "timestamp": "2026-02-28T00:00:00Z",
        "soil_moisture": 0.28,
        "temperature_c": 27.5,
        "humidity_pct": 65.0,
        "wind_speed_mps": 2.1,
    }
    r = await client.post("/api/v1/sensors/ingest", json=payload)
    assert r.status_code == 202
    assert r.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_latest_sensors(client):
    r = await client.get("/api/v1/sensors/latest")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_create_alert(client):
    r = await client.post("/api/v1/alerts/", json={
        "alert_type": "SYSTEM",
        "severity": "INFO",
        "message": "Test alert from pytest",
    })
    assert r.status_code == 201
    assert "alert_id" in r.json()


@pytest.mark.asyncio
async def test_weather_endpoint(client):
    r = await client.get("/api/v1/weather")
    assert r.status_code == 200
    data = r.json()
    assert "temperature_c" in data
    assert "rain_probability" in data
