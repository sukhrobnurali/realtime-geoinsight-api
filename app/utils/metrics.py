"""
Prometheus metrics collection and monitoring utilities.
"""

from prometheus_client import (
    Counter, Histogram, Gauge, Info, 
    generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, REGISTRY
)
from typing import Dict, Any, Optional, List
import time
from functools import wraps
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import psutil
import asyncio
import logging

logger = logging.getLogger(__name__)


class GeospatialMetrics:
    """Comprehensive metrics collection for geospatial API operations."""
    
    def __init__(self):
        # API Metrics
        self.http_requests_total = Counter(
            'http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status_code']
        )
        
        self.http_request_duration = Histogram(
            'http_request_duration_seconds',
            'HTTP request duration in seconds',
            ['method', 'endpoint'],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )
        
        self.http_request_size = Histogram(
            'http_request_size_bytes',
            'HTTP request size in bytes',
            ['method', 'endpoint'],
            buckets=[100, 1000, 10000, 100000, 1000000]
        )
        
        self.http_response_size = Histogram(
            'http_response_size_bytes',
            'HTTP response size in bytes',
            ['method', 'endpoint'],
            buckets=[100, 1000, 10000, 100000, 1000000]
        )
        
        # Database Metrics
        self.db_queries_total = Counter(
            'db_queries_total',
            'Total database queries',
            ['operation', 'table', 'status']
        )
        
        self.db_query_duration = Histogram(
            'db_query_duration_seconds',
            'Database query duration in seconds',
            ['operation', 'table'],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
        )
        
        self.db_connections = Gauge(
            'db_connections_active',
            'Active database connections'
        )
        
        # Geospatial Specific Metrics
        self.spatial_operations_total = Counter(
            'spatial_operations_total',
            'Total spatial operations',
            ['operation_type', 'status']
        )
        
        self.spatial_operation_duration = Histogram(
            'spatial_operation_duration_seconds',
            'Spatial operation duration in seconds',
            ['operation_type'],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
        )
        
        self.geofence_checks_total = Counter(
            'geofence_checks_total',
            'Total geofence intersection checks',
            ['user_id', 'result']
        )
        
        self.device_locations_updated = Counter(
            'device_locations_updated_total',
            'Total device location updates',
            ['user_id', 'device_type']
        )
        
        self.route_optimizations_total = Counter(
            'route_optimizations_total',
            'Total route optimizations',
            ['algorithm', 'waypoint_count_range']
        )
        
        self.recommendations_served = Counter(
            'recommendations_served_total',
            'Total recommendations served',
            ['recommendation_type', 'user_id']
        )
        
        # Cache Metrics
        self.cache_operations_total = Counter(
            'cache_operations_total',
            'Total cache operations',
            ['operation', 'cache_type', 'result']
        )
        
        self.cache_hit_ratio = Gauge(
            'cache_hit_ratio',
            'Cache hit ratio',
            ['cache_type']
        )
        
        # System Metrics
        self.system_cpu_usage = Gauge(
            'system_cpu_usage_percent',
            'System CPU usage percentage'
        )
        
        self.system_memory_usage = Gauge(
            'system_memory_usage_bytes',
            'System memory usage in bytes'
        )
        
        self.system_disk_usage = Gauge(
            'system_disk_usage_bytes',
            'System disk usage in bytes'
        )
        
        # Business Metrics
        self.active_users = Gauge(
            'active_users_total',
            'Number of active users'
        )
        
        self.active_devices = Gauge(
            'active_devices_total',
            'Number of active devices'
        )
        
        self.api_key_usage = Counter(
            'api_key_usage_total',
            'API key usage count',
            ['api_key_id', 'endpoint']
        )
        
        # Error Metrics
        self.errors_total = Counter(
            'errors_total',
            'Total errors',
            ['error_type', 'component', 'severity']
        )
        
        self.error_rate = Gauge(
            'error_rate_percent',
            'Error rate percentage',
            ['component']
        )
        
        # Performance Metrics
        self.response_compression_ratio = Histogram(
            'response_compression_ratio',
            'Response compression ratio',
            ['content_type'],
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        )
        
        self.concurrent_requests = Gauge(
            'concurrent_requests_active',
            'Number of concurrent requests being processed'
        )


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP metrics automatically."""
    
    def __init__(self, app, metrics: GeospatialMetrics):
        super().__init__(app)
        self.metrics = metrics
        self.concurrent_requests = 0
    
    async def dispatch(self, request: Request, call_next):
        # Track concurrent requests
        self.concurrent_requests += 1
        self.metrics.concurrent_requests.set(self.concurrent_requests)
        
        start_time = time.time()
        method = request.method
        path = request.url.path
        
        # Get request size
        request_size = int(request.headers.get('content-length', 0))
        
        try:
            response = await call_next(request)
            status_code = response.status_code
            
            # Get response size
            response_size = 0
            if hasattr(response, 'body'):
                response_size = len(response.body)
            
            # Record metrics
            duration = time.time() - start_time
            
            self.metrics.http_requests_total.labels(
                method=method,
                endpoint=self._normalize_path(path),
                status_code=status_code
            ).inc()
            
            self.metrics.http_request_duration.labels(
                method=method,
                endpoint=self._normalize_path(path)
            ).observe(duration)
            
            if request_size > 0:
                self.metrics.http_request_size.labels(
                    method=method,
                    endpoint=self._normalize_path(path)
                ).observe(request_size)
            
            if response_size > 0:
                self.metrics.http_response_size.labels(
                    method=method,
                    endpoint=self._normalize_path(path)
                ).observe(response_size)
            
            return response
            
        except Exception as e:
            # Record error metrics
            self.metrics.errors_total.labels(
                error_type=type(e).__name__,
                component='api',
                severity='error'
            ).inc()
            
            raise
        finally:
            self.concurrent_requests -= 1
            self.metrics.concurrent_requests.set(self.concurrent_requests)
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path for metrics to avoid high cardinality."""
        # Replace UUIDs and IDs with placeholders
        import re
        
        # Replace UUID patterns
        path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{id}', path)
        
        # Replace numeric IDs
        path = re.sub(r'/\d+(?=/|$)', '/{id}', path)
        
        return path


def track_operation(operation_type: str, component: str = 'general'):
    """Decorator to track operation metrics."""
    
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                
                # Record success
                metrics.spatial_operations_total.labels(
                    operation_type=operation_type,
                    status='success'
                ).inc()
                
                return result
                
            except Exception as e:
                # Record error
                metrics.spatial_operations_total.labels(
                    operation_type=operation_type,
                    status='error'
                ).inc()
                
                metrics.errors_total.labels(
                    error_type=type(e).__name__,
                    component=component,
                    severity='error'
                ).inc()
                
                raise
            finally:
                duration = time.time() - start_time
                metrics.spatial_operation_duration.labels(
                    operation_type=operation_type
                ).observe(duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                
                metrics.spatial_operations_total.labels(
                    operation_type=operation_type,
                    status='success'
                ).inc()
                
                return result
                
            except Exception as e:
                metrics.spatial_operations_total.labels(
                    operation_type=operation_type,
                    status='error'
                ).inc()
                
                metrics.errors_total.labels(
                    error_type=type(e).__name__,
                    component=component,
                    severity='error'
                ).inc()
                
                raise
            finally:
                duration = time.time() - start_time
                metrics.spatial_operation_duration.labels(
                    operation_type=operation_type
                ).observe(duration)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


class SystemMetricsCollector:
    """Collect system-level metrics."""
    
    def __init__(self, metrics: GeospatialMetrics):
        self.metrics = metrics
        self.running = False
    
    async def start_collection(self, interval_seconds: int = 30):
        """Start collecting system metrics at regular intervals."""
        self.running = True
        
        while self.running:
            try:
                await self._collect_system_metrics()
                await asyncio.sleep(interval_seconds)
            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
                await asyncio.sleep(interval_seconds)
    
    def stop_collection(self):
        """Stop collecting system metrics."""
        self.running = False
    
    async def _collect_system_metrics(self):
        """Collect current system metrics."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.metrics.system_cpu_usage.set(cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.metrics.system_memory_usage.set(memory.used)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.metrics.system_disk_usage.set(disk.used)
            
        except Exception as e:
            logger.warning(f"Could not collect system metrics: {e}")


class BusinessMetricsCollector:
    """Collect business-specific metrics."""
    
    def __init__(self, metrics: GeospatialMetrics):
        self.metrics = metrics
    
    async def update_active_users(self, db_session):
        """Update active users count."""
        try:
            # Count users active in last 24 hours
            from sqlalchemy import text
            
            query = text("""
                SELECT COUNT(DISTINCT user_id) 
                FROM devices 
                WHERE last_seen > NOW() - INTERVAL '24 hours'
            """)
            
            result = await db_session.execute(query)
            count = result.scalar()
            
            self.metrics.active_users.set(count or 0)
            
        except Exception as e:
            logger.warning(f"Could not update active users metric: {e}")
    
    async def update_active_devices(self, db_session):
        """Update active devices count."""
        try:
            from sqlalchemy import text
            
            query = text("""
                SELECT COUNT(*) 
                FROM devices 
                WHERE last_seen > NOW() - INTERVAL '1 hour'
            """)
            
            result = await db_session.execute(query)
            count = result.scalar()
            
            self.metrics.active_devices.set(count or 0)
            
        except Exception as e:
            logger.warning(f"Could not update active devices metric: {e}")


class CacheMetricsTracker:
    """Track cache performance metrics."""
    
    def __init__(self, metrics: GeospatialMetrics):
        self.metrics = metrics
        self.cache_stats = {}
    
    def record_cache_operation(self, operation: str, cache_type: str, result: str):
        """Record cache operation (hit/miss/error)."""
        self.metrics.cache_operations_total.labels(
            operation=operation,
            cache_type=cache_type,
            result=result
        ).inc()
        
        # Update hit ratio
        self._update_hit_ratio(cache_type, result)
    
    def _update_hit_ratio(self, cache_type: str, result: str):
        """Update cache hit ratio."""
        if cache_type not in self.cache_stats:
            self.cache_stats[cache_type] = {'hits': 0, 'misses': 0}
        
        if result == 'hit':
            self.cache_stats[cache_type]['hits'] += 1
        elif result == 'miss':
            self.cache_stats[cache_type]['misses'] += 1
        
        stats = self.cache_stats[cache_type]
        total = stats['hits'] + stats['misses']
        
        if total > 0:
            hit_ratio = stats['hits'] / total
            self.metrics.cache_hit_ratio.labels(cache_type=cache_type).set(hit_ratio)


# Global metrics instance
metrics = GeospatialMetrics()
system_collector = SystemMetricsCollector(metrics)
business_collector = BusinessMetricsCollector(metrics)
cache_tracker = CacheMetricsTracker(metrics)


def get_metrics_response() -> Response:
    """Generate Prometheus metrics response."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST
    )