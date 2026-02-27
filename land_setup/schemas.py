from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class SoilType(str, Enum):
    CLAY = "clay"
    SANDY = "sandy"
    LOAMY = "loamy"
    SILTY = "silty"
    PEATY = "peaty"
    CHALKY = "chalky"


class CropType(str, Enum):
    WHEAT = "wheat"
    RICE = "rice"
    MAIZE = "maize"
    COTTON = "cotton"
    SUGARCANE = "sugarcane"
    VEGETABLES = "vegetables"
    TOMATO = "tomato"
    POTATO = "potato"


class TopologyType(str, Enum):
    FLAT = "flat"
    SLOPED = "sloped"
    TERRACED = "terraced"
    HILLY = "hilly"


class Coordinate(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude")


class FieldBoundary(BaseModel):
    type: str = Field(default="Polygon", description="GeoJSON geometry type")
    coordinates: list[Coordinate] = Field(
        ..., min_length=3, description="Polygon vertices (minimum 3 points)"
    )


class SoilData(BaseModel):
    soil_type: SoilType
    ph: float = Field(..., ge=0.0, le=14.0, description="Soil pH level")
    organic_matter_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Organic matter percentage"
    )
    field_capacity: float = Field(
        ..., ge=0.0, le=1.0,
        description="Soil volumetric water content at field capacity (0–1)"
    )
    wilting_point: float = Field(
        ..., ge=0.0, le=1.0,
        description="Permanent wilting point volumetric moisture (0–1)"
    )

    @field_validator("wilting_point")
    @classmethod
    def wilting_below_field_capacity(cls, v: float, info: any) -> float:
        fc = info.data.get("field_capacity", 1.0)
        if v >= fc:
            raise ValueError(
                f"wilting_point ({v}) must be less than field_capacity ({fc})"
            )
        return v


class TopologyData(BaseModel):
    type: TopologyType
    elevation_m: float = Field(..., description="Average elevation in metres")
    slope_degrees: float = Field(0.0, ge=0.0, le=90.0, description="Average slope in degrees")
    drainage_class: str = Field(
        default="well-drained",
        description="Drainage class (e.g. well-drained, poorly-drained)"
    )


class NodeLocation(BaseModel):
    node_id: str = Field(..., description="Unique sensor node identifier")
    zone_id: str = Field(..., description="Zone this node belongs to")
    coordinate: Coordinate
    depth_cm: float = Field(
        10.0, ge=0.0, le=200.0,
        description="Sensor installation depth in cm"
    )
    description: Optional[str] = None


class FarmProfile(BaseModel):
    farm_id: str = Field(..., description="Unique farm identifier")
    farm_name: str
    owner: str
    location: str = Field(..., description="Human-readable location (city, region)")
    total_area_ha: float = Field(..., gt=0.0, description="Total farm area in hectares")
    soil: SoilData
    topology: TopologyData
    crop_type: CropType
    boundary: FieldBoundary
    nodes: list[NodeLocation] = Field(default_factory=list)
    created_at: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("nodes")
    @classmethod
    def nodes_must_have_unique_ids(cls, v: list[NodeLocation]) -> list[NodeLocation]:
        ids = [n.node_id for n in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Node IDs must be unique within a farm profile")
        return v
