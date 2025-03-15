"""
Device Service
Handles business logic for device management, location tracking, and trajectory analysis.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import selectinload
from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_MakePoint
from geoalchemy2.elements import WKTElement

from app.models.device import Device
from app.models.trajectory import Trajectory, TrajectoryPoint
from app.models.user import User
from app.schemas.device import (
    DeviceCreate, DeviceUpdate, LocationUpdate, DeviceStats, 
    NearbyDevices, DeviceProximity, TrajectoryDetail
)
from app.services.redis_client import redis_client


class DeviceService:
    """Service for managing devices and location tracking."""

    @staticmethod
    async def create_device(
        db: AsyncSession, 
        device_data: DeviceCreate, 
        user_id: str
    ) -> Device:
        """Create a new device for a user."""
        device = Device(
            user_id=user_id,
            device_name=device_data.device_name,
            device_identifier=device_data.device_identifier
        )
        
        db.add(device)
        await db.commit()
        await db.refresh(device)
        return device

    @staticmethod
    async def get_user_devices(
        db: AsyncSession, 
        user_id: str, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Device]:
        """Get all devices for a user."""
        result = await db.execute(
            select(Device)
            .where(Device.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .order_by(Device.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_device_by_id(
        db: AsyncSession, 
        device_id: str, 
        user_id: str
    ) -> Optional[Device]:
        """Get a specific device by ID, ensuring user ownership."""
        result = await db.execute(
            select(Device)
            .where(and_(Device.id == device_id, Device.user_id == user_id))
        )
        return result.scalars().first()

    @staticmethod
    async def update_device(
        db: AsyncSession, 
        device_id: str, 
        user_id: str, 
        device_data: DeviceUpdate
    ) -> Optional[Device]:
        """Update device information."""
        device = await DeviceService.get_device_by_id(db, device_id, user_id)
        if not device:
            return None

        update_data = device_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(device, field, value)

        device.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(device)
        return device

    @staticmethod
    async def delete_device(
        db: AsyncSession, 
        device_id: str, 
        user_id: str
    ) -> bool:
        """Delete a device and all associated data."""
        device = await DeviceService.get_device_by_id(db, device_id, user_id)
        if not device:
            return False

        await db.delete(device)
        await db.commit()
        
        # Clean up Redis cache
        await redis_client.delete(f"device:{device_id}:location")
        return True

    @staticmethod
    async def update_device_location(
        db: AsyncSession, 
        device_id: str, 
        user_id: str, 
        location_data: LocationUpdate
    ) -> Optional[Device]:
        """Update device location and handle trajectory tracking."""
        device = await DeviceService.get_device_by_id(db, device_id, user_id)
        if not device:
            return None

        # Create WKT point for PostGIS
        point_wkt = f"POINT({location_data.longitude} {location_data.latitude})"
        
        # Update device location
        device.last_location = WKTElement(point_wkt, srid=4326)
        device.last_seen = location_data.timestamp or datetime.utcnow()
        device.updated_at = datetime.utcnow()

        # Store in Redis for real-time access
        location_cache = {
            "latitude": location_data.latitude,
            "longitude": location_data.longitude,
            "timestamp": device.last_seen.isoformat(),
            "speed": location_data.speed,
            "heading": location_data.heading,
            "accuracy": location_data.accuracy,
            "altitude": location_data.altitude
        }
        await redis_client.setex(
            f"device:{device_id}:location", 
            3600,  # 1 hour expiry
            str(location_cache)
        )

        # Handle trajectory tracking
        await DeviceService._add_trajectory_point(db, device, location_data)

        await db.commit()
        await db.refresh(device)
        return device

    @staticmethod
    async def _add_trajectory_point(
        db: AsyncSession, 
        device: Device, 
        location_data: LocationUpdate
    ):
        """Add a new trajectory point and manage trajectory segments."""
        # Get or create current trajectory
        current_time = location_data.timestamp or datetime.utcnow()
        
        # Check if we have an active trajectory (within last hour)
        result = await db.execute(
            select(Trajectory)
            .where(
                and_(
                    Trajectory.device_id == device.id,
                    Trajectory.end_time >= current_time - timedelta(hours=1)
                )
            )
            .order_by(Trajectory.end_time.desc())
            .limit(1)
        )
        trajectory = result.scalars().first()

        # Create new trajectory if none exists or if gap is too large
        if not trajectory:
            trajectory = Trajectory(
                device_id=device.id,
                start_time=current_time,
                end_time=current_time,
                point_count=0
            )
            db.add(trajectory)
            await db.flush()  # Get the ID

        # Add trajectory point
        point_wkt = f"POINT({location_data.longitude} {location_data.latitude})"
        trajectory_point = TrajectoryPoint(
            trajectory_id=trajectory.id,
            location=WKTElement(point_wkt, srid=4326),
            timestamp=current_time,
            speed=location_data.speed,
            heading=location_data.heading,
            accuracy=location_data.accuracy,
            altitude=location_data.altitude
        )
        db.add(trajectory_point)

        # Update trajectory statistics
        trajectory.end_time = current_time
        trajectory.point_count = (trajectory.point_count or 0) + 1
        
        # Update speed statistics
        if location_data.speed:
            if not trajectory.max_speed or location_data.speed > trajectory.max_speed:
                trajectory.max_speed = location_data.speed

    @staticmethod
    async def get_device_trajectory(
        db: AsyncSession,
        device_id: str,
        user_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[TrajectoryDetail]:
        """Get device trajectory data with optional time filtering."""
        device = await DeviceService.get_device_by_id(db, device_id, user_id)
        if not device:
            return []

        query = select(Trajectory).where(Trajectory.device_id == device_id)
        
        if start_time:
            query = query.where(Trajectory.start_time >= start_time)
        if end_time:
            query = query.where(Trajectory.end_time <= end_time)
            
        query = query.order_by(Trajectory.start_time.desc()).limit(limit)
        
        result = await db.execute(query)
        trajectories = result.scalars().all()
        
        return [
            TrajectoryDetail(
                id=str(traj.id),
                device_id=str(traj.device_id),
                start_time=traj.start_time,
                end_time=traj.end_time,
                total_distance=traj.total_distance,
                avg_speed=traj.avg_speed,
                max_speed=traj.max_speed,
                point_count=traj.point_count or 0
            )
            for traj in trajectories
        ]

    @staticmethod
    async def get_nearby_devices(
        db: AsyncSession,
        user_id: str,
        latitude: float,
        longitude: float,
        radius_meters: float = 1000,
        limit: int = 50
    ) -> NearbyDevices:
        """Find devices within a specified radius."""
        # Create point for search
        search_point = func.ST_GeogFromText(f"POINT({longitude} {latitude})")
        
        # Query for nearby devices
        result = await db.execute(
            select(
                Device,
                ST_Distance(Device.last_location, search_point).label('distance')
            )
            .where(
                and_(
                    Device.user_id == user_id,
                    Device.last_location.isnot(None),
                    ST_DWithin(Device.last_location, search_point, radius_meters)
                )
            )
            .order_by(text('distance'))
            .limit(limit)
        )
        
        devices_with_distance = result.all()
        
        nearby_devices = [
            DeviceProximity(
                device_id=str(device.id),
                device_name=device.device_name,
                distance_meters=float(distance),
                last_seen=device.last_seen
            )
            for device, distance in devices_with_distance
        ]
        
        return NearbyDevices(
            center_latitude=latitude,
            center_longitude=longitude,
            radius_meters=radius_meters,
            total_found=len(nearby_devices),
            devices=nearby_devices
        )

    @staticmethod
    async def get_device_statistics(
        db: AsyncSession,
        device_id: str,
        user_id: str,
        days: int = 30
    ) -> Optional[DeviceStats]:
        """Get comprehensive statistics for a device."""
        device = await DeviceService.get_device_by_id(db, device_id, user_id)
        if not device:
            return None

        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get trajectory statistics
        result = await db.execute(
            select(
                func.count(TrajectoryPoint.id).label('total_points'),
                func.avg(TrajectoryPoint.speed).label('avg_speed'),
                func.max(TrajectoryPoint.speed).label('max_speed'),
                func.sum(Trajectory.total_distance).label('total_distance')
            )
            .select_from(TrajectoryPoint)
            .join(Trajectory, TrajectoryPoint.trajectory_id == Trajectory.id)
            .where(
                and_(
                    Trajectory.device_id == device_id,
                    TrajectoryPoint.timestamp >= start_date
                )
            )
        )
        stats = result.first()
        
        # Get recent trajectory count
        trajectory_result = await db.execute(
            select(func.count(Trajectory.id))
            .where(
                and_(
                    Trajectory.device_id == device_id,
                    Trajectory.start_time >= start_date
                )
            )
        )
        trajectory_count = trajectory_result.scalar()

        return DeviceStats(
            device_id=str(device.id),
            device_name=device.device_name,
            total_distance_meters=float(stats.total_distance or 0),
            total_trajectories=trajectory_count or 0,
            total_location_points=stats.total_points or 0,
            average_speed_ms=float(stats.avg_speed or 0),
            max_speed_ms=float(stats.max_speed or 0),
            last_seen=device.last_seen,
            days_analyzed=days
        )

    @staticmethod
    async def bulk_update_locations(
        db: AsyncSession,
        user_id: str,
        updates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Handle bulk location updates for multiple devices."""
        results = {
            "successful": [],
            "failed": [],
            "total_processed": len(updates)
        }
        
        for update_data in updates:
            try:
                device_id = update_data.get("device_id")
                location_update = LocationUpdate(**update_data)
                
                device = await DeviceService.update_device_location(
                    db, device_id, user_id, location_update
                )
                
                if device:
                    results["successful"].append(device_id)
                else:
                    results["failed"].append({
                        "device_id": device_id,
                        "error": "Device not found"
                    })
                    
            except Exception as e:
                results["failed"].append({
                    "device_id": update_data.get("device_id", "unknown"),
                    "error": str(e)
                })
        
        return results


# Singleton instance
device_service = DeviceService()