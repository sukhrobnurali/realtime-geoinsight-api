from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from enum import Enum


class GeofenceType(str, Enum):
    CIRCLE = "circle"
    POLYGON = "polygon"
    RECTANGLE = "rectangle"


class GeometryType(str, Enum):
    POINT = "Point"
    POLYGON = "Polygon"
    CIRCLE = "Circle"


class Coordinates(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lon: float = Field(..., ge=-180, le=180, description="Longitude")
    
    class Config:
        schema_extra = {
            "example": {
                "lat": 40.7589,
                "lon": -73.9851
            }
        }


class CircleGeometry(BaseModel):
    type: str = "Circle"
    center: Coordinates
    radius: float = Field(..., gt=0, description="Radius in meters")
    
    class Config:
        schema_extra = {
            "example": {
                "type": "Circle",
                "center": {"lat": 40.7589, "lon": -73.9851},
                "radius": 100
            }
        }


class PolygonGeometry(BaseModel):
    type: str = "Polygon"
    coordinates: List[List[List[float]]] = Field(..., description="GeoJSON polygon coordinates")
    
    @validator('coordinates')
    def validate_polygon(cls, v):
        if not v or not v[0] or len(v[0]) < 4:
            raise ValueError("Polygon must have at least 4 coordinates")
        
        # Check if polygon is closed (first and last points are the same)
        if v[0][0] != v[0][-1]:
            raise ValueError("Polygon must be closed (first and last points must be the same)")
        
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "type": "Polygon",
                "coordinates": [[
                    [-73.9851, 40.7589],
                    [-73.9851, 40.7614],
                    [-73.9813, 40.7614],
                    [-73.9813, 40.7589],
                    [-73.9851, 40.7589]
                ]]
            }
        }


class GeofenceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: bool = True
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class GeofenceCreate(GeofenceBase):
    geometry: Dict[str, Any] = Field(..., description="Geofence geometry (Circle or Polygon)")
    
    @validator('geometry')
    def validate_geometry(cls, v):
        if v.get('type') == 'Circle':
            CircleGeometry(**v)
        elif v.get('type') == 'Polygon':
            PolygonGeometry(**v)
        else:
            raise ValueError("Geometry type must be 'Circle' or 'Polygon'")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "name": "Office Building",
                "description": "Main office building geofence",
                "is_active": True,
                "metadata": {"department": "IT", "priority": "high"},
                "geometry": {
                    "type": "Circle",
                    "center": {"lat": 40.7589, "lon": -73.9851},
                    "radius": 100
                }
            }
        }


class GeofenceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    geometry: Optional[Dict[str, Any]] = Field(None, description="Updated geometry")
    
    @validator('geometry')
    def validate_geometry(cls, v):
        if v is None:
            return v
        if v.get('type') == 'Circle':
            CircleGeometry(**v)
        elif v.get('type') == 'Polygon':
            PolygonGeometry(**v)
        else:
            raise ValueError("Geometry type must be 'Circle' or 'Polygon'")
        return v


class Geofence(GeofenceBase):
    id: uuid.UUID
    user_id: uuid.UUID
    geometry_type: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class GeofenceDetail(Geofence):
    geometry: Dict[str, Any]
    
    class Config:
        from_attributes = True


class GeofenceCheckRequest(BaseModel):
    location: Coordinates
    geofence_ids: Optional[List[uuid.UUID]] = Field(None, description="Specific geofences to check, if None checks all active geofences")
    
    class Config:
        schema_extra = {
            "example": {
                "location": {"lat": 40.7589, "lon": -73.9851},
                "geofence_ids": ["123e4567-e89b-12d3-a456-426614174000"]
            }
        }


class GeofenceCheckResult(BaseModel):
    location: Coordinates
    inside_geofences: List[uuid.UUID]
    outside_geofences: List[uuid.UUID]
    total_checked: int
    
    class Config:
        schema_extra = {
            "example": {
                "location": {"lat": 40.7589, "lon": -73.9851},
                "inside_geofences": ["123e4567-e89b-12d3-a456-426614174000"],
                "outside_geofences": ["456e4567-e89b-12d3-a456-426614174001"],
                "total_checked": 2
            }
        }


class GeofenceEvent(BaseModel):
    device_id: uuid.UUID
    geofence_id: uuid.UUID
    event_type: str = Field(..., regex="^(enter|exit)$")
    location: Coordinates
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    class Config:
        schema_extra = {
            "example": {
                "device_id": "789e4567-e89b-12d3-a456-426614174002",
                "geofence_id": "123e4567-e89b-12d3-a456-426614174000",
                "event_type": "enter",
                "location": {"lat": 40.7589, "lon": -73.9851},
                "timestamp": "2025-03-11T10:30:00Z",
                "metadata": {"speed": 5.2, "heading": 45}
            }
        }


class WebhookConfig(BaseModel):
    url: str = Field(..., regex=r'^https?://.+', description="Webhook endpoint URL")
    events: List[str] = Field(..., description="Events to trigger webhook (enter, exit)")
    headers: Optional[Dict[str, str]] = Field(default_factory=dict)
    is_active: bool = True
    
    @validator('events')
    def validate_events(cls, v):
        valid_events = {'enter', 'exit'}
        if not all(event in valid_events for event in v):
            raise ValueError(f"Events must be one of: {valid_events}")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "url": "https://api.example.com/webhooks/geofence",
                "events": ["enter", "exit"],
                "headers": {"Authorization": "Bearer token123"},
                "is_active": True
            }
        }