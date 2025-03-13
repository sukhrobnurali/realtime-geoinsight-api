from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from geoalchemy2 import functions as spatial_functions
from geoalchemy2.elements import WKTElement
from shapely.geometry import Point, Polygon
from shapely import wkt
import json
import uuid

from app.models.geofence import Geofence
from app.models.user import User
from app.schemas.geofence import (
    GeofenceCreate, GeofenceUpdate, GeofenceCheckRequest, 
    GeofenceCheckResult, GeofenceEvent, Coordinates
)


class GeofenceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_geofence(self, user_id: uuid.UUID, geofence_data: GeofenceCreate) -> Geofence:
        """Create a new geofence"""
        # Convert geometry to PostGIS format
        geometry_wkt = self._convert_geometry_to_wkt(geofence_data.geometry)
        
        db_geofence = Geofence(
            user_id=user_id,
            name=geofence_data.name,
            description=geofence_data.description,
            geometry=WKTElement(geometry_wkt, srid=4326),
            metadata=geofence_data.metadata or {},
            is_active=geofence_data.is_active
        )
        
        self.db.add(db_geofence)
        await self.db.commit()
        await self.db.refresh(db_geofence)
        
        return db_geofence

    async def get_geofences(
        self, 
        user_id: uuid.UUID, 
        skip: int = 0, 
        limit: int = 100,
        is_active: Optional[bool] = None
    ) -> List[Geofence]:
        """Get user's geofences with pagination"""
        query = select(Geofence).where(Geofence.user_id == user_id)
        
        if is_active is not None:
            query = query.where(Geofence.is_active == is_active)
        
        query = query.offset(skip).limit(limit).order_by(Geofence.created_at.desc())
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_geofence(self, user_id: uuid.UUID, geofence_id: uuid.UUID) -> Optional[Geofence]:
        """Get a specific geofence"""
        result = await self.db.execute(
            select(Geofence).where(
                and_(Geofence.id == geofence_id, Geofence.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()

    async def update_geofence(
        self, 
        user_id: uuid.UUID, 
        geofence_id: uuid.UUID, 
        geofence_update: GeofenceUpdate
    ) -> Optional[Geofence]:
        """Update a geofence"""
        geofence = await self.get_geofence(user_id, geofence_id)
        if not geofence:
            return None
        
        update_data = geofence_update.dict(exclude_unset=True)
        
        # Handle geometry update
        if 'geometry' in update_data:
            geometry_wkt = self._convert_geometry_to_wkt(update_data['geometry'])
            update_data['geometry'] = WKTElement(geometry_wkt, srid=4326)
        
        for field, value in update_data.items():
            setattr(geofence, field, value)
        
        await self.db.commit()
        await self.db.refresh(geofence)
        
        return geofence

    async def delete_geofence(self, user_id: uuid.UUID, geofence_id: uuid.UUID) -> bool:
        """Delete a geofence"""
        geofence = await self.get_geofence(user_id, geofence_id)
        if not geofence:
            return False
        
        await self.db.delete(geofence)
        await self.db.commit()
        return True

    async def check_point_in_geofences(
        self, 
        user_id: uuid.UUID, 
        check_request: GeofenceCheckRequest
    ) -> GeofenceCheckResult:
        """Check if a point is inside geofences"""
        lat, lon = check_request.location.lat, check_request.location.lon
        point = f"POINT({lon} {lat})"
        
        # Build query
        query = select(Geofence).where(
            and_(
                Geofence.user_id == user_id,
                Geofence.is_active == True
            )
        )
        
        if check_request.geofence_ids:
            query = query.where(Geofence.id.in_(check_request.geofence_ids))
        
        result = await self.db.execute(query)
        geofences = result.scalars().all()
        
        inside_geofences = []
        outside_geofences = []
        
        for geofence in geofences:
            # Use PostGIS ST_Contains function
            contains_query = select(
                spatial_functions.ST_Contains(geofence.geometry, WKTElement(point, srid=4326))
            )
            contains_result = await self.db.execute(contains_query)
            is_inside = contains_result.scalar()
            
            if is_inside:
                inside_geofences.append(geofence.id)
            else:
                outside_geofences.append(geofence.id)
        
        return GeofenceCheckResult(
            location=check_request.location,
            inside_geofences=inside_geofences,
            outside_geofences=outside_geofences,
            total_checked=len(geofences)
        )

    async def get_geofences_containing_point(
        self, 
        user_id: uuid.UUID, 
        lat: float, 
        lon: float
    ) -> List[Geofence]:
        """Get all geofences that contain a specific point"""
        point = WKTElement(f"POINT({lon} {lat})", srid=4326)
        
        query = select(Geofence).where(
            and_(
                Geofence.user_id == user_id,
                Geofence.is_active == True,
                spatial_functions.ST_Contains(Geofence.geometry, point)
            )
        )
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_geofences_within_distance(
        self, 
        user_id: uuid.UUID, 
        lat: float, 
        lon: float, 
        distance_meters: float
    ) -> List[Tuple[Geofence, float]]:
        """Get geofences within a certain distance from a point"""
        point = WKTElement(f"POINT({lon} {lat})", srid=4326)
        
        query = select(
            Geofence,
            spatial_functions.ST_Distance(
                spatial_functions.ST_Transform(Geofence.geometry, 3857),
                spatial_functions.ST_Transform(point, 3857)
            ).label('distance')
        ).where(
            and_(
                Geofence.user_id == user_id,
                Geofence.is_active == True,
                spatial_functions.ST_DWithin(
                    spatial_functions.ST_Transform(Geofence.geometry, 3857),
                    spatial_functions.ST_Transform(point, 3857),
                    distance_meters
                )
            )
        ).order_by('distance')
        
        result = await self.db.execute(query)
        return [(row.Geofence, row.distance) for row in result]

    def _convert_geometry_to_wkt(self, geometry: Dict[str, Any]) -> str:
        """Convert geometry dict to WKT string"""
        geom_type = geometry.get('type')
        
        if geom_type == 'Circle':
            # Convert circle to polygon approximation
            center = geometry['center']
            radius_meters = geometry['radius']
            
            # Create a polygon approximation of the circle
            # Convert radius from meters to degrees (rough approximation)
            radius_degrees = radius_meters / 111320  # meters per degree at equator
            
            center_point = Point(center['lon'], center['lat'])
            circle_polygon = center_point.buffer(radius_degrees)
            
            return circle_polygon.wkt
            
        elif geom_type == 'Polygon':
            # Convert GeoJSON polygon to Shapely polygon
            coords = geometry['coordinates'][0]  # Exterior ring
            polygon = Polygon(coords)
            return polygon.wkt
            
        else:
            raise ValueError(f"Unsupported geometry type: {geom_type}")

    def _convert_wkt_to_geometry(self, wkt_string: str, geometry_type: str) -> Dict[str, Any]:
        """Convert WKT string back to geometry dict"""
        geom = wkt.loads(wkt_string)
        
        if geometry_type == 'Circle':
            # For circles, we need to store the original center and radius
            # This is a simplification - in practice, you'd store this metadata
            centroid = geom.centroid
            # Approximate radius from bounding box
            bounds = geom.bounds
            radius_degrees = (bounds[2] - bounds[0]) / 2
            radius_meters = radius_degrees * 111320  # rough conversion
            
            return {
                'type': 'Circle',
                'center': {'lat': centroid.y, 'lon': centroid.x},
                'radius': radius_meters
            }
        else:
            # Polygon
            coords = list(geom.exterior.coords)
            return {
                'type': 'Polygon',
                'coordinates': [coords]
            }

    async def get_geofence_statistics(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Get statistics about user's geofences"""
        total_query = select(func.count(Geofence.id)).where(Geofence.user_id == user_id)
        active_query = select(func.count(Geofence.id)).where(
            and_(Geofence.user_id == user_id, Geofence.is_active == True)
        )
        
        total_result = await self.db.execute(total_query)
        active_result = await self.db.execute(active_query)
        
        total_geofences = total_result.scalar()
        active_geofences = active_result.scalar()
        
        return {
            'total_geofences': total_geofences,
            'active_geofences': active_geofences,
            'inactive_geofences': total_geofences - active_geofences
        }