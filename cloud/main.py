from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cloud.database import init_db
from cloud.ws_manager import ws_manager
from cloud.weather_service import weather_service
from cloud.routers import sensors, irrigation, alerts, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(
    title = "SAMS Cloud API",
    description="Smart Agriculture Monitoring System — Cloud Backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sensors.router)
app.include_router(irrigation.router)
app.include_router(alerts.router)
app.include_router(admin.router)

@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "service": "sams-cloud", "version": "1.0.0"}

@app.websocket("/ws/stream")
async def websocket_stream(ws: WebSocket):
    await ws_manager.connect(ws, topic="global")
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, topic="global")


@app.get("/api/v1/weather", tags=["weather"])
async def get_weather():
    forecast = await weather_service.get_forecast()
    return weather_service.to_dict(forecast)

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "SAMS Cloud API — visit /docs for API reference"}
