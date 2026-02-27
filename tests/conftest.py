import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("WEATHER_MODE", "mock")
os.environ.setdefault("ML_MODEL_TYPE", "rf")
