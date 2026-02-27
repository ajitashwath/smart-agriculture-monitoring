import pytest
from cloud.weather_service import WeatherService


@pytest.mark.asyncio
async def test_mock_mode_returns_forecast():
    svc = WeatherService()
    fc = await svc.get_forecast()
    assert fc is not None
    assert fc.source == "mock"
    assert 0 <= fc.rain_probability <= 1
    assert fc.temperature_c > 0


@pytest.mark.asyncio
async def test_cache_returns_same_object():
    svc = WeatherService()
    fc1 = await svc.get_forecast()
    fc2 = await svc.get_forecast()
    assert fc1.timestamp == fc2.timestamp   # same cached object


@pytest.mark.asyncio
async def test_to_dict():
    svc = WeatherService()
    fc = await svc.get_forecast()
    d = svc.to_dict(fc)
    assert "temperature_c" in d
    assert "rain_probability" in d
    assert "source" in d
