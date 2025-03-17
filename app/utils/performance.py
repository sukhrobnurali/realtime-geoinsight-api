"""
Performance optimization utilities and query helpers.
"""

from typing import Dict, Any, List, Optional, Union, Tuple
from sqlalchemy import text, select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_Intersects, ST_Contains
import asyncio
from contextlib import asynccontextmanager
import time
import logging

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """Optimized query patterns for geospatial operations."""
    
    @staticmethod
    async def get_nearby_devices_optimized(
        db: AsyncSession,
        user_id: str,
        latitude: float,
        longitude: float,
        radius_meters: float,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Optimized query for nearby devices using spatial indexes."""
        
        # Use optimized spatial query with proper index hints
        query = text("""
            SELECT 
                d.id,
                d.device_name,
                d.last_seen,
                ST_Distance(d.last_location, ST_Point(:longitude, :latitude)::geography) as distance_meters
            FROM devices d
            WHERE d.user_id = :user_id
              AND d.last_location IS NOT NULL
              AND ST_DWithin(
                  d.last_location, 
                  ST_Point(:longitude, :latitude)::geography, 
                  :radius_meters
              )
            ORDER BY d.last_location <-> ST_Point(:longitude, :latitude)::geography
            LIMIT :limit
        """)
        
        result = await db.execute(query, {
            "user_id": user_id,
            "latitude": latitude,
            "longitude": longitude,
            "radius_meters": radius_meters,
            "limit": limit
        })
        
        return [dict(row._mapping) for row in result.fetchall()]
    
    @staticmethod
    async def get_geofence_intersections_optimized(
        db: AsyncSession,
        user_id: str,
        latitude: float,
        longitude: float
    ) -> List[Dict[str, Any]]:
        """Optimized query for geofence intersections."""
        
        query = text("""
            SELECT 
                g.id,
                g.name,
                g.metadata,
                ST_Distance(ST_Centroid(g.geometry), ST_Point(:longitude, :latitude)::geography) as distance_to_center
            FROM geofences g
            WHERE g.user_id = :user_id
              AND ST_Contains(g.geometry, ST_Point(:longitude, :latitude)::geography)
            ORDER BY distance_to_center
        """)
        
        result = await db.execute(query, {
            "user_id": user_id,
            "latitude": latitude,
            "longitude": longitude
        })
        
        return [dict(row._mapping) for row in result.fetchall()]
    
    @staticmethod
    async def get_trajectory_analytics_optimized(
        db: AsyncSession,
        device_id: str,
        start_time: str,
        end_time: str
    ) -> Dict[str, Any]:
        """Optimized trajectory analytics using covering indexes."""
        
        query = text("""
            WITH trajectory_stats AS (
                SELECT 
                    COUNT(*) as point_count,
                    AVG(speed) as avg_speed,
                    MAX(speed) as max_speed,
                    MIN(timestamp) as first_point,
                    MAX(timestamp) as last_point,
                    ST_Distance(
                        (SELECT location FROM trajectory_points WHERE trajectory_id = t.id ORDER BY timestamp LIMIT 1),
                        (SELECT location FROM trajectory_points WHERE trajectory_id = t.id ORDER BY timestamp DESC LIMIT 1)
                    ) as direct_distance
                FROM trajectories t
                JOIN trajectory_points tp ON t.id = tp.trajectory_id
                WHERE t.device_id = :device_id
                  AND tp.timestamp BETWEEN :start_time AND :end_time
                GROUP BY t.id
            )
            SELECT 
                SUM(point_count) as total_points,
                AVG(avg_speed) as overall_avg_speed,
                MAX(max_speed) as overall_max_speed,
                SUM(direct_distance) as total_distance
            FROM trajectory_stats
        """)
        
        result = await db.execute(query, {
            "device_id": device_id,
            "start_time": start_time,
            "end_time": end_time
        })
        
        row = result.fetchone()
        return dict(row._mapping) if row else {}
    
    @staticmethod
    async def batch_distance_calculation(
        db: AsyncSession,
        origin_points: List[Tuple[float, float]],
        destination_points: List[Tuple[float, float]]
    ) -> List[List[float]]:
        """Optimized batch distance matrix calculation."""
        
        # Build efficient batch query
        origins_sql = ", ".join([
            f"ST_Point({lon}, {lat})::geography" 
            for lat, lon in origin_points
        ])
        
        destinations_sql = ", ".join([
            f"ST_Point({lon}, {lat})::geography" 
            for lat, lon in destination_points
        ])
        
        query = text(f"""
            WITH origins AS (
                SELECT unnest(ARRAY[{origins_sql}]) as origin_point
            ),
            destinations AS (
                SELECT unnest(ARRAY[{destinations_sql}]) as dest_point
            )
            SELECT 
                ST_Distance(o.origin_point, d.dest_point) as distance
            FROM origins o
            CROSS JOIN destinations d
            ORDER BY o.origin_point, d.dest_point
        """)
        
        result = await db.execute(query)
        distances = [row[0] for row in result.fetchall()]
        
        # Reshape into matrix
        num_destinations = len(destination_points)
        matrix = []
        for i in range(len(origin_points)):
            start_idx = i * num_destinations
            end_idx = start_idx + num_destinations
            matrix.append(distances[start_idx:end_idx])
        
        return matrix


class ConnectionPoolOptimizer:
    """Database connection pool optimization."""
    
    @staticmethod
    def get_optimized_pool_settings() -> Dict[str, Any]:
        """Get optimized connection pool settings."""
        return {
            "pool_size": 20,  # Base connection pool size
            "max_overflow": 30,  # Additional connections under load
            "pool_timeout": 30,  # Timeout for getting connection
            "pool_recycle": 3600,  # Recycle connections every hour
            "pool_pre_ping": True,  # Validate connections before use
            "connect_args": {
                "server_settings": {
                    "application_name": "geoinsight_api",
                    "jit": "off",  # Disable JIT for better predictability
                }
            }
        }


class CacheManager:
    """Advanced caching strategies for geospatial data."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.default_ttl = 3600  # 1 hour
        
    async def cache_spatial_query(
        self,
        cache_key: str,
        query_func,
        ttl: Optional[int] = None
    ) -> Any:
        """Cache spatial query results with automatic invalidation."""
        
        # Try to get from cache first
        cached_result = await self.redis.get(cache_key)
        if cached_result:
            return eval(cached_result)  # In production, use proper serialization
        
        # Execute query and cache result
        result = await query_func()
        await self.redis.setex(
            cache_key,
            ttl or self.default_ttl,
            str(result)
        )
        
        return result
    
    async def invalidate_spatial_cache(self, pattern: str):
        """Invalidate cached spatial queries by pattern."""
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)
    
    def generate_spatial_cache_key(
        self,
        operation: str,
        user_id: str,
        latitude: float,
        longitude: float,
        radius: float,
        **kwargs
    ) -> str:
        """Generate consistent cache keys for spatial operations."""
        lat_rounded = round(latitude, 6)
        lon_rounded = round(longitude, 6)
        radius_rounded = round(radius, 2)
        
        extra_params = "_".join([f"{k}_{v}" for k, v in sorted(kwargs.items())])
        
        return f"spatial:{operation}:{user_id}:{lat_rounded}:{lon_rounded}:{radius_rounded}:{extra_params}"


class PerformanceMonitor:
    """Performance monitoring and profiling utilities."""
    
    @staticmethod
    @asynccontextmanager
    async def measure_query_time(operation_name: str):
        """Context manager to measure query execution time."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            logger.info(f"Query {operation_name} took {duration:.3f}s")
            
            # In production, send to monitoring system
            # metrics.histogram('query_duration', duration, tags={'operation': operation_name})
    
    @staticmethod
    async def analyze_slow_queries(db: AsyncSession, min_duration_ms: int = 1000):
        """Analyze slow queries from PostgreSQL logs."""
        
        query = text("""
            SELECT 
                query,
                mean_exec_time,
                calls,
                total_exec_time,
                min_exec_time,
                max_exec_time,
                stddev_exec_time
            FROM pg_stat_statements
            WHERE mean_exec_time > :min_duration
            ORDER BY mean_exec_time DESC
            LIMIT 20
        """)
        
        try:
            result = await db.execute(query, {"min_duration": min_duration_ms})
            return [dict(row._mapping) for row in result.fetchall()]
        except Exception as e:
            logger.warning(f"Could not analyze slow queries: {e}")
            return []
    
    @staticmethod
    async def get_index_usage_stats(db: AsyncSession) -> List[Dict[str, Any]]:
        """Get index usage statistics."""
        
        query = text("""
            SELECT 
                schemaname,
                tablename,
                indexname,
                idx_tup_read,
                idx_tup_fetch,
                idx_scan
            FROM pg_stat_user_indexes
            WHERE schemaname = 'public'
            ORDER BY idx_scan DESC
        """)
        
        try:
            result = await db.execute(query)
            return [dict(row._mapping) for row in result.fetchall()]
        except Exception as e:
            logger.warning(f"Could not get index stats: {e}")
            return []


class BatchProcessor:
    """Batch processing utilities for high-throughput operations."""
    
    @staticmethod
    async def process_location_updates_batch(
        db: AsyncSession,
        location_updates: List[Dict[str, Any]],
        batch_size: int = 100
    ):
        """Process location updates in optimized batches."""
        
        for i in range(0, len(location_updates), batch_size):
            batch = location_updates[i:i + batch_size]
            
            # Build bulk update query
            case_clauses = []
            device_ids = []
            
            for update in batch:
                device_id = update["device_id"]
                lat = update["latitude"]
                lon = update["longitude"]
                timestamp = update["timestamp"]
                
                device_ids.append(device_id)
                case_clauses.append(f"""
                    WHEN id = '{device_id}' THEN ST_Point({lon}, {lat})::geography
                """)
            
            if case_clauses:
                query = text(f"""
                    UPDATE devices
                    SET 
                        last_location = CASE 
                            {''.join(case_clauses)}
                        END,
                        last_seen = NOW(),
                        updated_at = NOW()
                    WHERE id = ANY(:device_ids)
                """)
                
                await db.execute(query, {"device_ids": device_ids})
        
        await db.commit()
    
    @staticmethod
    async def bulk_geofence_check(
        db: AsyncSession,
        device_locations: List[Dict[str, Any]],
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Bulk geofence intersection checking."""
        
        # Build locations array for efficient spatial query
        locations_sql = ", ".join([
            f"ST_Point({loc['longitude']}, {loc['latitude']})::geography"
            for loc in device_locations
        ])
        
        device_ids_sql = ", ".join([f"'{loc['device_id']}'" for loc in device_locations])
        
        query = text(f"""
            WITH device_locations AS (
                SELECT 
                    unnest(ARRAY[{device_ids_sql}]) as device_id,
                    unnest(ARRAY[{locations_sql}]) as location
            )
            SELECT 
                dl.device_id,
                g.id as geofence_id,
                g.name as geofence_name
            FROM device_locations dl
            JOIN geofences g ON g.user_id = :user_id
            WHERE ST_Contains(g.geometry, dl.location)
        """)
        
        result = await db.execute(query, {"user_id": user_id})
        return [dict(row._mapping) for row in result.fetchall()]


# Global instances
query_optimizer = QueryOptimizer()
performance_monitor = PerformanceMonitor()
batch_processor = BatchProcessor()