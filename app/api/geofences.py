from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.database import get_async_session
from app.schemas.geofence import (
    GeofenceCreate, GeofenceUpdate, Geofence, GeofenceDetail,
    GeofenceCheckRequest, GeofenceCheckResult, WebhookConfig
)
from app.services.geofence_service import GeofenceService
from app.services.webhook_service import WebhookService
from app.utils.dependencies import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/geofences", tags=["Geofences"])


@router.post("/", response_model=Geofence, status_code=status.HTTP_201_CREATED)
async def create_geofence(
    geofence_data: GeofenceCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Create a new geofence"""
    geofence_service = GeofenceService(db)
    return await geofence_service.create_geofence(current_user.id, geofence_data)


@router.get("/", response_model=List[Geofence])
async def list_geofences(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """List user's geofences with pagination"""
    geofence_service = GeofenceService(db)
    return await geofence_service.get_geofences(
        current_user.id, skip=skip, limit=limit, is_active=is_active
    )


@router.get("/statistics")
async def get_geofence_statistics(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get geofence statistics for the current user"""
    geofence_service = GeofenceService(db)
    return await geofence_service.get_geofence_statistics(current_user.id)


@router.get("/{geofence_id}", response_model=GeofenceDetail)
async def get_geofence(
    geofence_id: uuid.UUID = Path(..., description="Geofence ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get a specific geofence by ID"""
    geofence_service = GeofenceService(db)
    geofence = await geofence_service.get_geofence(current_user.id, geofence_id)
    
    if not geofence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geofence not found"
        )
    
    # Convert geometry for response
    # Note: In a real implementation, you'd want to properly convert the PostGIS geometry
    # back to the original format. For now, we'll return a simplified structure.
    return GeofenceDetail(
        id=geofence.id,
        user_id=geofence.user_id,
        name=geofence.name,
        description=geofence.description,
        is_active=geofence.is_active,
        metadata=geofence.metadata,
        geometry_type="Polygon",  # Simplified
        geometry={"type": "Polygon", "coordinates": []},  # Simplified
        created_at=geofence.created_at,
        updated_at=geofence.updated_at
    )


@router.put("/{geofence_id}", response_model=Geofence)
async def update_geofence(
    geofence_update: GeofenceUpdate,
    geofence_id: uuid.UUID = Path(..., description="Geofence ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Update a geofence"""
    geofence_service = GeofenceService(db)
    geofence = await geofence_service.update_geofence(
        current_user.id, geofence_id, geofence_update
    )
    
    if not geofence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geofence not found"
        )
    
    return geofence


@router.delete("/{geofence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_geofence(
    geofence_id: uuid.UUID = Path(..., description="Geofence ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Delete a geofence"""
    geofence_service = GeofenceService(db)
    success = await geofence_service.delete_geofence(current_user.id, geofence_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geofence not found"
        )


@router.post("/check", response_model=GeofenceCheckResult)
async def check_geofences(
    check_request: GeofenceCheckRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Check if a location is inside any geofences"""
    geofence_service = GeofenceService(db)
    return await geofence_service.check_point_in_geofences(current_user.id, check_request)


@router.get("/nearby/point")
async def get_nearby_geofences(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    distance: float = Query(1000, ge=1, le=50000, description="Distance in meters"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get geofences within a certain distance from a point"""
    geofence_service = GeofenceService(db)
    results = await geofence_service.get_geofences_within_distance(
        current_user.id, lat, lon, distance
    )
    
    return [
        {
            "geofence": {
                "id": geofence.id,
                "name": geofence.name,
                "description": geofence.description,
                "is_active": geofence.is_active,
                "created_at": geofence.created_at
            },
            "distance_meters": distance
        }
        for geofence, distance in results
    ]


@router.get("/containing/point")
async def get_containing_geofences(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get all geofences that contain a specific point"""
    geofence_service = GeofenceService(db)
    geofences = await geofence_service.get_geofences_containing_point(
        current_user.id, lat, lon
    )
    
    return [
        {
            "id": geofence.id,
            "name": geofence.name,
            "description": geofence.description,
            "is_active": geofence.is_active,
            "metadata": geofence.metadata,
            "created_at": geofence.created_at
        }
        for geofence in geofences
    ]


@router.post("/{geofence_id}/webhook", status_code=status.HTTP_201_CREATED)
async def register_webhook(
    webhook_config: WebhookConfig,
    geofence_id: uuid.UUID = Path(..., description="Geofence ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Register a webhook for geofence events"""
    # Verify geofence exists and belongs to user
    geofence_service = GeofenceService(db)
    geofence = await geofence_service.get_geofence(current_user.id, geofence_id)
    
    if not geofence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geofence not found"
        )
    
    webhook_service = WebhookService(db)
    success = await webhook_service.register_webhook(
        current_user.id, geofence_id, webhook_config
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register webhook"
        )
    
    return {"message": "Webhook registered successfully"}


@router.get("/{geofence_id}/webhook", response_model=WebhookConfig)
async def get_webhook(
    geofence_id: uuid.UUID = Path(..., description="Geofence ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Get webhook configuration for a geofence"""
    # Verify geofence exists and belongs to user
    geofence_service = GeofenceService(db)
    geofence = await geofence_service.get_geofence(current_user.id, geofence_id)
    
    if not geofence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geofence not found"
        )
    
    webhook_service = WebhookService(db)
    webhook_config = await webhook_service.get_webhooks_for_geofence(
        current_user.id, geofence_id
    )
    
    if not webhook_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No webhook configured for this geofence"
        )
    
    return webhook_config


@router.delete("/{geofence_id}/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def remove_webhook(
    geofence_id: uuid.UUID = Path(..., description="Geofence ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Remove webhook configuration for a geofence"""
    # Verify geofence exists and belongs to user
    geofence_service = GeofenceService(db)
    geofence = await geofence_service.get_geofence(current_user.id, geofence_id)
    
    if not geofence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geofence not found"
        )
    
    webhook_service = WebhookService(db)
    success = await webhook_service.remove_webhook(current_user.id, geofence_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove webhook"
        )