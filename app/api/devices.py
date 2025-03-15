"""
Device Management API Endpoints
Provides REST API for device registration, location tracking, and analytics.
"""

from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.services.device_service import device_service
from app.schemas.device import (
    Device as DeviceSchema,
    DeviceCreate,
    DeviceUpdate,
    LocationUpdate,
    DeviceStats,
    NearbyDevices,
    TrajectoryDetail,
    BulkLocationUpdate
)

router = APIRouter()


@router.post("/", response_model=DeviceSchema, status_code=status.HTTP_201_CREATED)
async def create_device(
    device_data: DeviceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new device for the authenticated user.
    
    - **device_name**: Human-readable name for the device
    - **device_identifier**: Unique identifier (IMEI, UUID, etc.)
    """
    device = await device_service.create_device(
        db=db,
        device_data=device_data,
        user_id=str(current_user.id)
    )
    
    return DeviceSchema(
        id=str(device.id),
        user_id=str(device.user_id),
        device_name=device.device_name,
        device_identifier=device.device_identifier,
        last_seen=device.last_seen,
        created_at=device.created_at,
        updated_at=device.updated_at
    )


@router.get("/", response_model=List[DeviceSchema])
async def list_devices(
    skip: int = Query(0, ge=0, description="Number of devices to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of devices to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all devices for the authenticated user.
    
    Supports pagination with skip and limit parameters.
    """
    devices = await device_service.get_user_devices(
        db=db,
        user_id=str(current_user.id),
        skip=skip,
        limit=limit
    )
    
    return [
        DeviceSchema(
            id=str(device.id),
            user_id=str(device.user_id),
            device_name=device.device_name,
            device_identifier=device.device_identifier,
            last_seen=device.last_seen,
            created_at=device.created_at,
            updated_at=device.updated_at
        )
        for device in devices
    ]


@router.get("/{device_id}", response_model=DeviceSchema)
async def get_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific device by ID.
    
    Returns 404 if device doesn't exist or doesn't belong to the user.
    """
    device = await device_service.get_device_by_id(
        db=db,
        device_id=device_id,
        user_id=str(current_user.id)
    )
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    return DeviceSchema(
        id=str(device.id),
        user_id=str(device.user_id),
        device_name=device.device_name,
        device_identifier=device.device_identifier,
        last_seen=device.last_seen,
        created_at=device.created_at,
        updated_at=device.updated_at
    )


@router.put("/{device_id}", response_model=DeviceSchema)
async def update_device(
    device_id: str,
    device_data: DeviceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update device information.
    
    Only the device owner can update the device.
    """
    device = await device_service.update_device(
        db=db,
        device_id=device_id,
        user_id=str(current_user.id),
        device_data=device_data
    )
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    return DeviceSchema(
        id=str(device.id),
        user_id=str(device.user_id),
        device_name=device.device_name,
        device_identifier=device.device_identifier,
        last_seen=device.last_seen,
        created_at=device.created_at,
        updated_at=device.updated_at
    )


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a device and all associated tracking data.
    
    This action cannot be undone.
    """
    success = await device_service.delete_device(
        db=db,
        device_id=device_id,
        user_id=str(current_user.id)
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )


@router.put("/{device_id}/location", response_model=DeviceSchema)
async def update_device_location(
    device_id: str,
    location_data: LocationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update device location and track movement.
    
    This endpoint handles real-time location updates and automatically
    manages trajectory tracking and geofence monitoring.
    
    - **latitude**: Latitude in decimal degrees (-90 to 90)
    - **longitude**: Longitude in decimal degrees (-180 to 180)
    - **timestamp**: Optional timestamp (defaults to current time)
    - **speed**: Speed in meters per second
    - **heading**: Direction in degrees (0-360)
    - **accuracy**: GPS accuracy in meters
    - **altitude**: Altitude in meters
    """
    device = await device_service.update_device_location(
        db=db,
        device_id=device_id,
        user_id=str(current_user.id),
        location_data=location_data
    )
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    return DeviceSchema(
        id=str(device.id),
        user_id=str(device.user_id),
        device_name=device.device_name,
        device_identifier=device.device_identifier,
        last_seen=device.last_seen,
        created_at=device.created_at,
        updated_at=device.updated_at
    )


@router.get("/{device_id}/trajectory", response_model=List[TrajectoryDetail])
async def get_device_trajectory(
    device_id: str,
    start_time: Optional[datetime] = Query(None, description="Start time for trajectory data"),
    end_time: Optional[datetime] = Query(None, description="End time for trajectory data"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of trajectories to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get trajectory data for a device.
    
    Returns trajectory segments with optional time filtering.
    Each trajectory represents a continuous path of movement.
    """
    trajectories = await device_service.get_device_trajectory(
        db=db,
        device_id=device_id,
        user_id=str(current_user.id),
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    if not trajectories and not await device_service.get_device_by_id(
        db, device_id, str(current_user.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    return trajectories


@router.get("/{device_id}/stats", response_model=DeviceStats)
async def get_device_statistics(
    device_id: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive statistics for a device.
    
    Includes movement analytics, distance tracking, and usage patterns
    for the specified time period.
    """
    stats = await device_service.get_device_statistics(
        db=db,
        device_id=device_id,
        user_id=str(current_user.id),
        days=days
    )
    
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    return stats


@router.post("/nearby", response_model=NearbyDevices)
async def find_nearby_devices(
    latitude: float = Query(..., ge=-90, le=90, description="Center latitude"),
    longitude: float = Query(..., ge=-180, le=180, description="Center longitude"),
    radius_meters: float = Query(1000, gt=0, le=50000, description="Search radius in meters"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of devices to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Find devices within a specified radius of a location.
    
    Returns devices belonging to the authenticated user that are
    within the search radius, ordered by distance.
    """
    nearby_devices = await device_service.get_nearby_devices(
        db=db,
        user_id=str(current_user.id),
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
        limit=limit
    )
    
    return nearby_devices


@router.post("/locations/bulk")
async def bulk_update_locations(
    bulk_data: BulkLocationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update locations for multiple devices in a single request.
    
    Efficiently processes up to 1000 location updates at once.
    Returns summary of successful and failed updates.
    """
    if len(bulk_data.locations) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 1000 location updates per request"
        )
    
    # Convert to dict format for service
    updates = [
        {
            "device_id": loc.device_id,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "timestamp": loc.timestamp,
            "speed": loc.speed,
            "heading": loc.heading,
            "accuracy": loc.accuracy,
            "altitude": loc.altitude
        }
        for loc in bulk_data.locations
    ]
    
    results = await device_service.bulk_update_locations(
        db=db,
        user_id=str(current_user.id),
        updates=updates
    )
    
    return results