import asyncio
import pytest
from pump_control.controller import PumpController, PumpState


@pytest.fixture
def pump():
    return PumpController("pump-A", "zone-1", capacity_lph=1200.0, safety_timeout_seconds=60)


@pytest.mark.asyncio
async def test_pump_starts_off(pump):
    assert pump.state == PumpState.OFF
    assert not pump.is_on


@pytest.mark.asyncio
async def test_pump_on(pump):
    result = await pump.on(duration_minutes=5)
    assert result is True
    assert pump.is_on


@pytest.mark.asyncio
async def test_pump_idempotent(pump):
    await pump.on(duration_minutes=5)
    result = await pump.on(duration_minutes=5)
    assert result is False   # idempotent no-op
    await pump.off()


@pytest.mark.asyncio
async def test_pump_off_returns_log(pump):
    await pump.on(duration_minutes=5)
    await asyncio.sleep(0.05)
    log = await pump.off()
    assert log.pump_id == "pump-A"
    assert log.duration_seconds > 0
    assert pump.state == PumpState.OFF


@pytest.mark.asyncio
async def test_water_dispensed_positive(pump):
    await pump.on(duration_minutes=5)
    await asyncio.sleep(0.1)
    water = pump.water_dispensed_litres()
    assert water >= 0
    await pump.off()


@pytest.mark.asyncio
async def test_status_dict(pump):
    status = pump.status()
    assert "pump_id" in status
    assert "state" in status
    assert status["pump_id"] == "pump-A"
