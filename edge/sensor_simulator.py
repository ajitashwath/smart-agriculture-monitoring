from __future__ import annotations

import asyncio
import json
import math
import os
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "sams/sensors")
PUBLISH_INTERVAL = float(os.getenv("SENSOR_PUBLISH_INTERVAL", "5"))
NODE_COUNT = int(os.getenv("SENSOR_NODE_COUNT", "4"))
NOISE_FACTOR = float(os.getenv("SENSOR_NOISE_FACTOR", "0.05"))

NODE_IDS = [f"node-N{i+1}" for i in range(NODE_COUNT)]
ZONE_IDS = [f"zone-{i+1}" for i in range(NODE_COUNT)]


@dataclass
class SensorReading:
    node_id: str
    zone_id: str
    timestamp: str
    soil_moisture: float
    temperature_c: float
    humidity_pct: float
    wind_speed_mps: float
    battery_pct: float
    pest_alert: bool
    camera_event: bool
    signal_rssi: int


class SensorNodeState:
    def __init__(self, node_id: str, zone_id: str) -> None:
        self.node_id = node_id
        self.zone_id = zone_id
        self.moisture = random.uniform(0.25, 0.45)
        self.battery = random.uniform(75.0, 100.0)
        self._dry_trend = random.choice([True, False])
        self._drift_phase = random.uniform(0, 2 * math.pi)

    def _add_noise(self, value: float, scale: float) -> float:
        return value + random.gauss(0, scale * NOISE_FACTOR)

    def _diurnal_temp(self, hour: float) -> float:
        base = random.uniform(24.0, 30.0)
        return base + 6.0 * math.sin(math.pi * (hour - 6) / 12)

    def _diurnal_humidity(self, temp: float) -> float:
        return max(30.0, min(95.0, 85.0 - (temp - 20.0) * 1.2 + random.gauss(0, 3)))

    def update(self) -> SensorReading:
        now = datetime.now(tz=timezone.utc)
        hour = now.hour + now.minute / 60.0

        drift = -0.002 if self._dry_trend else 0.001
        self.moisture = max(0.10, min(0.55, self.moisture + drift + random.gauss(0, 0.003)))

        if self.moisture < 0.15:
            self._dry_trend = False
        if self.moisture > 0.48:
            self._dry_trend = True

        temp = self._add_noise(self._diurnal_temp(hour), 0.5)
        humidity = self._add_noise(self._diurnal_humidity(temp), 2.0)
        wind = max(0.0, random.gauss(2.5, 1.0))

        self.battery = max(5.0, self.battery - random.uniform(0.001, 0.005))

        pest_alert = random.random() < 0.03
        camera_event = random.random() < 0.02

        return SensorReading(
            node_id=self.node_id,
            zone_id=self.zone_id,
            timestamp=now.isoformat(),
            soil_moisture=round(self._add_noise(self.moisture, 0.01), 4),
            temperature_c=round(temp, 2),
            humidity_pct=round(humidity, 2),
            wind_speed_mps=round(wind, 2),
            battery_pct=round(self.battery, 1),
            pest_alert=pest_alert,
            camera_event=camera_event,
            signal_rssi=random.randint(-80, -40),
        )


class SensorSimulator:
    def __init__(self) -> None:
        self._nodes: List[SensorNodeState] = [
            SensorNodeState(NODE_IDS[i], ZONE_IDS[i]) for i in range(NODE_COUNT)
        ]
        self._client = mqtt.Client(client_id=f"simulator-{int(time.time())}")
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._connected = asyncio.Event()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[SensorSim] Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
            self._connected.set()
        else:
            print(f"[SensorSim] Connection failed with RC={rc}")

    def _on_disconnect(self, client, userdata, rc):
        print(f"[SensorSim] Disconnected from broker (RC={rc}), will reconnect...")
        self._connected.clear()

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.connect(MQTT_HOST, MQTT_PORT, keepalive=60),
        )
        self._client.loop_start()
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            raise ConnectionError(f"Could not connect to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")

    def _publish(self, reading: SensorReading) -> None:
        topic = f"{TOPIC_PREFIX}/{reading.node_id}"
        payload = json.dumps(asdict(reading))
        result = self._client.publish(topic, payload, qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"[SensorSim] Publish failed for {reading.node_id}: rc={result.rc}")

    async def run_forever(self) -> None:
        await self.connect()
        print(f"[SensorSim] Publishing {NODE_COUNT} nodes every {PUBLISH_INTERVAL}s …")
        while True:
            for node in self._nodes:
                reading = node.update()
                self._publish(reading)
                print(
                    f"[{reading.node_id}] moisture={reading.soil_moisture:.3f} "
                    f"temp={reading.temperature_c:.1f}°C "
                    f"humidity={reading.humidity_pct:.1f}%"
                )
            await asyncio.sleep(PUBLISH_INTERVAL)

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


async def main() -> None:
    sim = SensorSimulator()
    try:
        await sim.run_forever()
    except (KeyboardInterrupt, asyncio.CancelledError):
        sim.stop()
        print("[SensorSim] Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
