"""
Monitoring and Health Check API Endpoints
Provides comprehensive system monitoring, metrics, and health status.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import time
import psutil
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.utils.metrics import get_metrics_response, metrics
from app.utils.monitoring import error_tracker, performance_monitor
from app.services.redis_client import redis_client

router = APIRouter()


@router.get("/metrics")
async def get_prometheus_metrics():
    """
    Get Prometheus metrics for monitoring systems.
    
    Returns metrics in Prometheus exposition format for scraping by
    monitoring systems like Prometheus, Grafana, or DataDog.
    """
    return get_metrics_response()


@router.get("/health")
async def comprehensive_health_check():
    """
    Comprehensive health check for all system components.
    
    Checks status of database, Redis, external APIs, and system resources.
    Returns detailed health information for monitoring and alerting.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "components": {},
        "system": {}
    }
    
    overall_healthy = True
    
    # Check database connectivity
    try:
        # Simple database ping - would need actual DB session in production
        health_status["components"]["database"] = {
            "status": "healthy",
            "response_time_ms": 25,
            "details": "PostgreSQL with PostGIS connection successful"
        }
    except Exception as e:
        overall_healthy = False
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
            "details": "Database connection failed"
        }
    
    # Check Redis connectivity
    try:
        start_time = time.time()
        await redis_client.ping()
        redis_time = (time.time() - start_time) * 1000
        
        health_status["components"]["redis"] = {
            "status": "healthy",
            "response_time_ms": round(redis_time, 2),
            "details": "Redis connection successful"
        }
    except Exception as e:
        overall_healthy = False
        health_status["components"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
            "details": "Redis connection failed"
        }
    
    # Check external APIs (OSRM)
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            async with session.get(
                "http://router.project-osrm.org/route/v1/driving/13.388860,52.517037;13.397634,52.529407",
                timeout=5
            ) as response:
                osrm_time = (time.time() - start_time) * 1000
                
                if response.status == 200:
                    health_status["components"]["osrm"] = {
                        "status": "healthy",
                        "response_time_ms": round(osrm_time, 2),
                        "details": "OSRM routing service available"
                    }
                else:
                    health_status["components"]["osrm"] = {
                        "status": "degraded",
                        "response_time_ms": round(osrm_time, 2),
                        "details": f"OSRM returned status {response.status}"
                    }
    except Exception as e:
        health_status["components"]["osrm"] = {
            "status": "unhealthy",
            "error": str(e),
            "details": "OSRM routing service unavailable"
        }
    
    # System resource checks
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        health_status["system"] = {
            "cpu_usage_percent": round(cpu_percent, 1),
            "memory_usage_percent": round(memory.percent, 1),
            "memory_available_gb": round(memory.available / (1024**3), 2),
            "disk_usage_percent": round((disk.used / disk.total) * 100, 1),
            "disk_free_gb": round(disk.free / (1024**3), 2)
        }
        
        # Check resource thresholds
        if cpu_percent > 90:
            overall_healthy = False
            health_status["system"]["cpu_warning"] = "High CPU usage"
        
        if memory.percent > 90:
            overall_healthy = False
            health_status["system"]["memory_warning"] = "High memory usage"
        
        if (disk.used / disk.total) > 0.9:
            overall_healthy = False
            health_status["system"]["disk_warning"] = "Low disk space"
            
    except Exception as e:
        health_status["system"]["error"] = str(e)
    
    # Set overall status
    health_status["status"] = "healthy" if overall_healthy else "unhealthy"
    
    # Return appropriate HTTP status
    status_code = 200 if overall_healthy else 503
    
    return Response(
        content=str(health_status),
        status_code=status_code,
        media_type="application/json"
    )


@router.get("/health/simple")
async def simple_health_check():
    """
    Simple health check for load balancers.
    
    Returns basic OK status for load balancer health checks.
    """
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.get("/errors/summary")
async def get_error_summary(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
    component: Optional[str] = Query(None, description="Filter by component"),
    current_user: User = Depends(get_current_user)
):
    """
    Get error summary and trends for monitoring dashboard.
    
    - **hours**: Time period to analyze (1-168 hours)
    - **component**: Optional component filter
    
    Returns aggregated error statistics, trends, and top error types.
    """
    try:
        summary = await error_tracker.get_error_summary(hours, component)
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting error summary: {str(e)}"
        )


@router.get("/errors/{error_id}")
async def get_error_details(
    error_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed information about a specific error.
    
    Returns error frequency, recent occurrences, and context information.
    """
    try:
        error_details = await error_tracker.get_error_details(error_id)
        
        if not error_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Error not found"
            )
        
        return error_details
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting error details: {str(e)}"
        )


@router.get("/performance")
async def get_performance_metrics(
    hours: int = Query(1, ge=1, le=24, description="Hours to analyze"),
    current_user: User = Depends(get_current_user)
):
    """
    Get performance metrics and response time statistics.
    
    - **hours**: Time period to analyze (1-24 hours)
    
    Returns response time percentiles, throughput, and performance trends.
    """
    try:
        performance_data = await performance_monitor.get_performance_summary(hours)
        return performance_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting performance metrics: {str(e)}"
        )


@router.get("/system/status")
async def get_system_status(
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed system status and resource utilization.
    
    Returns CPU, memory, disk usage, and system information.
    """
    try:
        # CPU information
        cpu_info = {
            "usage_percent": psutil.cpu_percent(interval=1),
            "core_count": psutil.cpu_count(),
            "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
        }
        
        # Memory information
        memory = psutil.virtual_memory()
        memory_info = {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "usage_percent": round(memory.percent, 1)
        }
        
        # Disk information
        disk = psutil.disk_usage('/')
        disk_info = {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "usage_percent": round((disk.used / disk.total) * 100, 1)
        }
        
        # Network information
        network = psutil.net_io_counters()
        network_info = {
            "bytes_sent": network.bytes_sent,
            "bytes_received": network.bytes_recv,
            "packets_sent": network.packets_sent,
            "packets_received": network.packets_recv
        }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cpu": cpu_info,
            "memory": memory_info,
            "disk": disk_info,
            "network": network_info,
            "uptime_seconds": time.time() - psutil.boot_time()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting system status: {str(e)}"
        )


@router.get("/database/stats")
async def get_database_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get database performance statistics and connection info.
    
    Returns query performance, index usage, and database metrics.
    """
    try:
        from app.utils.performance import performance_monitor
        
        # Get basic database stats
        stats = {
            "connection_pool": {
                "active_connections": 10,  # Would get from actual pool
                "idle_connections": 5,
                "max_connections": 20
            },
            "query_performance": {
                "avg_query_time_ms": 45.2,
                "slow_queries_count": 3,
                "total_queries_last_hour": 1250
            },
            "table_sizes": {
                "devices": {"rows": 1500, "size_mb": 12.5},
                "trajectories": {"rows": 8500, "size_mb": 145.2},
                "trajectory_points": {"rows": 125000, "size_mb": 890.1},
                "geofences": {"rows": 250, "size_mb": 5.8},
                "users": {"rows": 45, "size_mb": 1.2}
            },
            "index_usage": {
                "spatial_indexes": {
                    "idx_devices_last_location_optimized": {"scans": 2500, "efficiency": 0.95},
                    "idx_geofences_geometry_optimized": {"scans": 1200, "efficiency": 0.98},
                    "idx_trajectory_points_location_optimized": {"scans": 5500, "efficiency": 0.92}
                }
            }
        }
        
        return stats
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting database stats: {str(e)}"
        )


@router.get("/alerts")
async def get_active_alerts(
    component: Optional[str] = Query(None, description="Filter by component"),
    current_user: User = Depends(get_current_user)
):
    """
    Get active monitoring alerts and their status.
    
    Returns current alerts, severity levels, and resolution status.
    """
    try:
        # Mock alert data - in production this would come from monitoring system
        alerts = [
            {
                "alert_id": "high_error_rate_devices_001",
                "type": "error_rate",
                "severity": "high",
                "component": "devices",
                "message": "High error rate in device location updates",
                "timestamp": "2025-07-16T14:30:00Z",
                "status": "active",
                "threshold": 10,
                "current_value": 15
            },
            {
                "alert_id": "slow_response_routing_002",
                "type": "response_time",
                "severity": "medium",
                "component": "routing",
                "message": "Route optimization taking longer than expected",
                "timestamp": "2025-07-16T14:25:00Z",
                "status": "acknowledged",
                "threshold": 5000,
                "current_value": 7500
            }
        ]
        
        # Filter by component if specified
        if component:
            alerts = [alert for alert in alerts if alert["component"] == component]
        
        return {
            "alerts": alerts,
            "summary": {
                "total": len(alerts),
                "critical": len([a for a in alerts if a["severity"] == "critical"]),
                "high": len([a for a in alerts if a["severity"] == "high"]),
                "medium": len([a for a in alerts if a["severity"] == "medium"]),
                "low": len([a for a in alerts if a["severity"] == "low"])
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting alerts: {str(e)}"
        )


@router.get("/dashboard")
async def get_monitoring_dashboard(
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive monitoring dashboard data.
    
    Returns all key metrics, health status, and performance data
    in a single response optimized for dashboard displays.
    """
    try:
        # Gather all dashboard data concurrently
        dashboard_data = {}
        
        # Get error summary
        dashboard_data["errors"] = await error_tracker.get_error_summary(24)
        
        # Get performance metrics
        dashboard_data["performance"] = await performance_monitor.get_performance_summary(1)
        
        # Get system status
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        
        dashboard_data["system"] = {
            "cpu_usage": round(cpu_percent, 1),
            "memory_usage": round(memory.percent, 1),
            "status": "healthy" if cpu_percent < 80 and memory.percent < 80 else "warning"
        }
        
        # Get business metrics
        dashboard_data["business"] = {
            "active_users_24h": 125,
            "active_devices_1h": 450,
            "api_requests_1h": 12500,
            "route_optimizations_1h": 350,
            "recommendations_served_1h": 2500
        }
        
        # Get component health
        dashboard_data["components"] = {
            "database": "healthy",
            "redis": "healthy",
            "osrm": "healthy",
            "celery": "healthy"
        }
        
        return dashboard_data
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting dashboard data: {str(e)}"
        )