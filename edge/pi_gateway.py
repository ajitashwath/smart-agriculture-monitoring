from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from edge.buffer import DiskBuffer

load_dotenv()

logger = logging.getLogger("sams.edge.gateway")

MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "sams/sensors")
CLOUD_URL = os.getenv("CLOUD_API_URL", "http://localhost:8000")
BUFFER_PATH = os.getenv("EDGE_BUFFER_PATH", "buffer/offline_queue.jsonl")
FORWARD_TIMEOUT = 5.0
DRAIN_INTERVAL = 30.0
MAX_RETRIES = 3


class EdgeDevice(ABC):
    @abstractmethod
    def get_device_info(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    def run_local_inference(self, features: Dict[str, float]) -> Optional[Dict]:
        ...


class RaspberryPiDevice(EdgeDevice):
    def get_device_info(self) -> Dict[str, Any]:
        return {
            "device_type": "raspberry-pi-4b",
            "arch": "aarch64",
            "cpu_cores": 4,
            "ram_gb": 4,
            "ml_accelerator": None,
            "firmware": "SAMS-Edge-2.0",
        }

    def run_local_inference(self, features: Dict[str, float]) -> Optional[Dict]:
        return None


def validate_reading(payload: dict) -> tuple[bool, str]:
    required = {"node_id", "zone_id", "timestamp", "soil_moisture", "temperature_c", "humidity_pct"}
    missing = required - payload.keys()
    if missing:
        return False, f"Missing fields: {missing}"

    sm = payload.get("soil_moisture", -1)
    if not (0.0 <= sm <= 1.0):
        return False, f"soil_moisture out of range: {sm}"

    temp = payload.get("temperature_c", -999)
    if not (-10.0 <= temp <= 60.0):
        return False, f"temperature_c out of range: {temp}"

    hum = payload.get("humidity_pct", -1)
    if not (0.0 <= hum <= 100.0):
        return False, f"humidity_pct out of range: {hum}"

    return True, "ok"


class PiGateway:
    def __init__(self, device: Optional[EdgeDevice] = None) -> None:
        self._device = device or RaspberryPiDevice()
        self._buffer = DiskBuffer(BUFFER_PATH)
        self._http: Optional[httpx.AsyncClient] = None
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._mqtt = mqtt.Client(client_id=f"sams-gateway-{int(time.time())}")
        self._mqtt.on_connect = self._on_mqtt_connect
        self._mqtt.on_message = self._on_mqtt_message

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            topic = f"{TOPIC_PREFIX}/#"
            client.subscribe(topic, qos=1)
            logger.info(f"Gateway connected to MQTT, subscribed to {topic}")
        else:
            logger.error(f"MQTT connect failed RC={rc}")

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            self._message_queue.put_nowait(payload)
        except (json.JSONDecodeError, asyncio.QueueFull) as exc:
            logger.warning(f"MQTT message dropped: {exc}")

    async def _forward(self, payload: dict) -> bool:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await self._http.post(
                    f"{CLOUD_URL}/api/v1/sensors/ingest",
                    json=payload,
                    timeout=FORWARD_TIMEOUT,
                )
                if resp.status_code in (200, 201, 202):
                    return True
                logger.warning(f"Cloud returned {resp.status_code} (attempt {attempt})")
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.warning(f"Network error attempt {attempt}: {exc}")
            await asyncio.sleep(2 ** attempt)
        return False

    async def _process_messages(self) -> None:
        while True:
            payload = await self._message_queue.get()
            valid, reason = validate_reading(payload)
            if not valid:
                logger.warning(f"Invalid reading from {payload.get('node_id')}: {reason}")
                continue

            payload["_gateway"] = self._device.get_device_info()
            payload["_received_at"] = datetime.now(tz=timezone.utc).isoformat()

            success = await self._forward(payload)
            if not success:
                self._buffer.enqueue(payload)
                logger.warning(f"Buffered reading for {payload.get('node_id')}")
            else:
                logger.debug(f"Forwarded reading for {payload.get('node_id')}")

    async def _drain_buffer(self) -> None:
        while True:
            await asyncio.sleep(DRAIN_INTERVAL)
            buffered = self._buffer.drain()
            if not buffered:
                continue
            logger.info(f"Draining {len(buffered)} buffered messages …")
            re_buffered = []
            for payload in buffered:
                if not await self._forward(payload):
                    re_buffered.append(payload)
            for p in re_buffered:
                self._buffer.enqueue(p)
            logger.info(f"  → {len(buffered) - len(re_buffered)} forwarded, "
                        f"{len(re_buffered)} still buffered")

    async def run(self) -> None:
        self._http = httpx.AsyncClient(base_url=CLOUD_URL)
        self._mqtt.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        self._mqtt.loop_start()
        logger.info(f"[Gateway] Device: {self._device.get_device_info()['device_type']}")
        logger.info(f"[Gateway] Listening on MQTT → forwarding to {CLOUD_URL}")
        try:
            await asyncio.gather(
                self._process_messages(),
                self._drain_buffer(),
            )
        finally:
            self._mqtt.loop_stop()
            await self._http.aclose()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    gateway = PiGateway()
    try:
        await gateway.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Gateway shutdown.")


if __name__ == "__main__":
    asyncio.run(main())
