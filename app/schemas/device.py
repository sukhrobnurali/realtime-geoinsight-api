from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from enum import Enum

from app.schemas.geofence import Coordinates


class DeviceStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    OFFLINE = "offline"


class DeviceBase(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=255)
    device_identifier: Optional[str] = Field(None, max_length=255, description="IMEI, UUID, or other unique identifier")
    
    class Config:
        schema_extra = {
            "example": {
                "device_name": "iPhone 13 Pro",
                "device_identifier": "358240051111110"
            }
        }


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    device_name: Optional[str] = Field(None, min_length=1, max_length=255)
    device_identifier: Optional[str] = Field(None, max_length=255)


class Device(DeviceBase):
    id: uuid.UUID
    user_id: uuid.UUID
    last_location: Optional[Coordinates] = None
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class LocationUpdate(BaseModel):
    location: Coordinates
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)
    speed: Optional[float] = Field(None, ge=0, description="Speed in m/s")
    heading: Optional[float] = Field(None, ge=0, lt=360, description="Heading in degrees")
    accuracy: Optional[float] = Field(None, ge=0, description="Location accuracy in meters")
    altitude: Optional[float] = Field(None, description="Altitude in meters")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    class Config:
        schema_extra = {
            "example": {
                "location": {"lat": 40.7589, "lon": -73.9851},
                "timestamp": "2025-03-12T10:30:00Z",
                "speed": 5.2,
                "heading": 45.0,
                "accuracy": 10.0,
                "altitude": 15.5,
                "metadata": {"battery_level": 85, "signal_strength": -70}
            }
        }


class TrajectoryBase(BaseModel):
    start_time: datetime
    end_time: datetime
    total_distance: Optional[float] = Field(None, ge=0, description="Total distance in meters")
    avg_speed: Optional[float] = Field(None, ge=0, description="Average speed in m/s")
    max_speed: Optional[float] = Field(None, ge=0, description="Maximum speed in m/s")
    point_count: int = Field(0, ge=0)


class Trajectory(TrajectoryBase):
    id: uuid.UUID
    device_id: uuid.UUID
    recorded_at: datetime
    
    class Config:
        from_attributes = True


class TrajectoryDetail(Trajectory):
    points: List[Dict[str, Any]] = Field(default_factory=list)


class TrajectoryPointCreate(BaseModel):
    location: Coordinates
    timestamp: datetime
    speed: Optional[float] = Field(None, ge=0)
    heading: Optional[float] = Field(None, ge=0, lt=360)
    accuracy: Optional[float] = Field(None, ge=0)
    altitude: Optional[float] = Field(None)


class TrajectoryPoint(TrajectoryPointCreate):
    id: uuid.UUID
    trajectory_id: uuid.UUID
    
    class Config:
        from_attributes = True


class DeviceStats(BaseModel):
    device_id: uuid.UUID
    total_distance: float = Field(0, description="Total distance traveled in meters")
    total_time: float = Field(0, description="Total tracking time in seconds")
    avg_speed: float = Field(0, description="Average speed in m/s")
    max_speed: float = Field(0, description="Maximum speed in m/s")
    location_count: int = Field(0, description="Total number of location points")
    trajectory_count: int = Field(0, description="Total number of trajectories")
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    
    class Config:
        schema_extra = {
            "example": {
                "device_id": "123e4567-e89b-12d3-a456-426614174000",
                "total_distance": 15432.5,
                "total_time": 3600.0,
                "avg_speed": 4.3,
                "max_speed": 25.0,
                "location_count": 1024,
                "trajectory_count": 15,
                "first_seen": "2025-03-01T08:00:00Z",
                "last_seen": "2025-03-12T10:30:00Z"
            }
        }


class LocationQuery(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(100, ge=1, le=10000)
    skip: int = Field(0, ge=0)
    min_accuracy: Optional[float] = Field(None, ge=0, description="Minimum accuracy filter")
    
    @validator('end_time')
    def validate_time_range(cls, v, values):
        if v and values.get('start_time') and v <= values['start_time']:
            raise ValueError('end_time must be after start_time')
        return v


class GeofenceAlert(BaseModel):
    device_id: uuid.UUID
    geofence_id: uuid.UUID
    alert_type: str = Field(..., regex="^(enter|exit)$")
    location: Coordinates
    timestamp: datetime
    geofence_name: str
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    class Config:
        schema_extra = {
            "example": {
                "device_id": "123e4567-e89b-12d3-a456-426614174000",
                "geofence_id": "456e4567-e89b-12d3-a456-426614174001",
                "alert_type": "enter",
                "location": {"lat": 40.7589, "lon": -73.9851},
                "timestamp": "2025-03-12T10:30:00Z",
                "geofence_name": "Office Building",
                "metadata": {"speed": 1.2, "confidence": 0.95}
            }
        }


class DeviceFilter(BaseModel):
    status: Optional[DeviceStatus] = None
    last_seen_after: Optional[datetime] = None
    last_seen_before: Optional[datetime] = None
    has_location: Optional[bool] = None
    name_contains: Optional[str] = None


class BulkLocationUpdate(BaseModel):
    device_id: uuid.UUID
    locations: List[LocationUpdate] = Field(..., min_items=1, max_items=1000)
    
    @validator('locations')
    def validate_locations_order(cls, v):
        # Ensure locations are in chronological order
        timestamps = [loc.timestamp for loc in v if loc.timestamp]
        if len(timestamps) > 1:
            for i in range(1, len(timestamps)):
                if timestamps[i] < timestamps[i-1]:
                    raise ValueError('Locations must be in chronological order')
        return v


class NearbyDevices(BaseModel):
    center: Coordinates
    radius_meters: float = Field(..., gt=0, le=50000)
    time_window_minutes: int = Field(60, gt=0, le=1440, description="Time window to look for devices")
    
    class Config:
        schema_extra = {
            "example": {
                "center": {"lat": 40.7589, "lon": -73.9851},
                "radius_meters": 1000,
                "time_window_minutes": 30
            }
        }


class DeviceProximity(BaseModel):
    device: Device
    distance_meters: float
    last_location: Coordinates
    last_seen: datetime