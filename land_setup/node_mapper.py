from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

MANIFEST_PATH = Path(__file__).parent / "zone_manifest.json"


@dataclass
class ZoneConfig:
    zone_id: str
    zone_name: str
    pump_id: str
    sensor_nodes: List[str]
    moisture_threshold: float
    irrigation_duration_minutes: int
    pump_capacity_lph: float
    crop_water_requirement_mm_day: float
    priority: int = 0

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "pump_id": self.pump_id,
            "sensor_nodes": self.sensor_nodes,
            "moisture_threshold": self.moisture_threshold,
            "irrigation_duration_minutes": self.irrigation_duration_minutes,
            "pump_capacity_lph": self.pump_capacity_lph,
            "crop_water_requirement_mm_day": self.crop_water_requirement_mm_day,
            "priority": self.priority,
        }


class NodeMapper:
    def __init__(self, manifest_path: Optional[Path] = None) -> None:
        path = manifest_path or MANIFEST_PATH
        self._zones: Dict[str, ZoneConfig] = {}
        self._node_to_zone: Dict[str, str] = {}
        self._pump_to_zones: Dict[str, List[str]] = {}
        self._load(path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Zone manifest not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        for z in manifest["zones"]:
            zone = ZoneConfig(
                zone_id=z["zone_id"],
                zone_name=z["zone_name"],
                pump_id=z["pump_id"],
                sensor_nodes=z["sensor_nodes"],
                moisture_threshold=float(z["moisture_threshold"]),
                irrigation_duration_minutes=int(z["irrigation_duration_minutes"]),
                pump_capacity_lph=float(z["pump_capacity_lph"]),
                crop_water_requirement_mm_day=float(z["crop_water_requirement_mm_day"]),
                priority=int(z.get("priority", 0)),
            )
            self._zones[zone.zone_id] = zone

            for node_id in zone.sensor_nodes:
                self._node_to_zone[node_id] = zone.zone_id

            self._pump_to_zones.setdefault(zone.pump_id, []).append(zone.zone_id)

    def get_zone(self, zone_id: str) -> Optional[ZoneConfig]:
        return self._zones.get(zone_id)

    def get_zone_for_node(self, node_id: str) -> Optional[ZoneConfig]:
        zone_id = self._node_to_zone.get(node_id)
        return self._zones.get(zone_id) if zone_id else None

    def get_zones_for_pump(self, pump_id: str) -> List[ZoneConfig]:
        return [self._zones[zid] for zid in self._pump_to_zones.get(pump_id, [])]

    def all_zones(self) -> List[ZoneConfig]:
        return sorted(self._zones.values(), key=lambda z: z.priority)

    def all_node_ids(self) -> List[str]:
        return list(self._node_to_zone.keys())

    def all_pump_ids(self) -> List[str]:
        return list(self._pump_to_zones.keys())

    def update_threshold(self, zone_id: str, new_threshold: float) -> None:
        if zone_id not in self._zones:
            raise KeyError(f"Zone '{zone_id}' not found")
        if not 0.0 <= new_threshold <= 1.0:
            raise ValueError(f"Threshold must be in [0, 1], got {new_threshold}")
        self._zones[zone_id].moisture_threshold = new_threshold

    def summary(self) -> List[dict]:
        return [z.to_dict() for z in self.all_zones()]
