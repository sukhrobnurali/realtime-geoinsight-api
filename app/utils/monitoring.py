"""
Error tracking and advanced monitoring utilities.
"""

import traceback
import json
import time
import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import logging

from app.services.redis_client import redis_client
from app.utils.logging import geo_logger


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Alert types for monitoring."""
    ERROR_RATE = "error_rate"
    RESPONSE_TIME = "response_time"
    DATABASE_CONNECTIVITY = "database_connectivity"
    MEMORY_USAGE = "memory_usage"
    DISK_SPACE = "disk_space"
    EXTERNAL_API = "external_api"


@dataclass
class ErrorEvent:
    """Structured error event for tracking."""
    error_id: str
    timestamp: datetime
    error_type: str
    error_message: str
    severity: ErrorSeverity
    component: str
    operation: str
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    stack_trace: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    frequency: int = 1
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


@dataclass
class PerformanceAlert:
    """Performance monitoring alert."""
    alert_id: str
    alert_type: AlertType
    message: str
    severity: ErrorSeverity
    timestamp: datetime
    threshold_value: float
    current_value: float
    component: str
    context: Optional[Dict[str, Any]] = None


class ErrorTracker:
    """Advanced error tracking and aggregation."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.error_retention_days = 30
        self.aggregation_window_minutes = 5
        
    async def track_error(
        self,
        error: Exception,
        component: str,
        operation: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Track and aggregate error events."""
        
        # Generate error fingerprint for deduplication
        error_fingerprint = self._generate_error_fingerprint(
            error, component, operation
        )
        
        # Create error event
        error_event = ErrorEvent(
            error_id=error_fingerprint,
            timestamp=datetime.utcnow(),
            error_type=type(error).__name__,
            error_message=str(error),
            severity=severity,
            component=component,
            operation=operation,
            user_id=user_id,
            request_id=request_id,
            stack_trace=traceback.format_exc(),
            context=context or {}
        )
        
        # Store/update error in Redis
        await self._store_error_event(error_event)
        
        # Check if this error requires immediate alerting
        await self._check_error_thresholds(error_event)
        
        # Log the error
        geo_logger.log_error(error, operation, context)
        
        return error_fingerprint
    
    async def get_error_summary(
        self,
        hours: int = 24,
        component: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get error summary for the specified time period."""
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        # Get error events from Redis
        error_events = await self._get_error_events(start_time, end_time, component)
        
        # Aggregate statistics
        total_errors = len(error_events)
        unique_errors = len(set(event.error_id for event in error_events))
        
        # Group by severity
        severity_counts = {}
        for severity in ErrorSeverity:
            severity_counts[severity.value] = len([
                e for e in error_events if e.severity == severity
            ])
        
        # Group by component
        component_counts = {}
        for event in error_events:
            component_counts[event.component] = component_counts.get(event.component, 0) + 1
        
        # Top error types
        error_type_counts = {}
        for event in error_events:
            error_type_counts[event.error_type] = error_type_counts.get(event.error_type, 0) + 1
        
        top_errors = sorted(
            error_type_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "time_period_hours": hours,
            "total_errors": total_errors,
            "unique_errors": unique_errors,
            "error_rate_per_hour": total_errors / hours if hours > 0 else 0,
            "severity_breakdown": severity_counts,
            "component_breakdown": component_counts,
            "top_error_types": dict(top_errors),
            "trends": await self._calculate_error_trends(error_events)
        }
    
    async def get_error_details(self, error_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific error."""
        
        error_key = f"error:{error_id}"
        error_data = await self.redis.get(error_key)
        
        if error_data:
            error_info = json.loads(error_data)
            
            # Get recent occurrences
            recent_key = f"error_occurrences:{error_id}"
            recent_occurrences = await self.redis.lrange(recent_key, 0, 50)
            
            error_info["recent_occurrences"] = [
                json.loads(occurrence) for occurrence in recent_occurrences
            ]
            
            return error_info
        
        return None
    
    def _generate_error_fingerprint(
        self,
        error: Exception,
        component: str,
        operation: str
    ) -> str:
        """Generate unique fingerprint for error deduplication."""
        
        # Create fingerprint from error type, message, and context
        fingerprint_data = {
            "error_type": type(error).__name__,
            "component": component,
            "operation": operation,
            # Use first line of error message to avoid minor variations
            "error_message": str(error).split('\n')[0][:200]
        }
        
        fingerprint_string = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.md5(fingerprint_string.encode()).hexdigest()
    
    async def _store_error_event(self, error_event: ErrorEvent):
        """Store error event in Redis with aggregation."""
        
        error_key = f"error:{error_event.error_id}"
        occurrence_key = f"error_occurrences:{error_event.error_id}"
        
        # Check if error already exists
        existing_error = await self.redis.get(error_key)
        
        if existing_error:
            # Update existing error
            error_data = json.loads(existing_error)
            error_data["frequency"] += 1
            error_data["last_seen"] = error_event.timestamp.isoformat()
            
            # Update severity if current is higher
            if ErrorSeverity(error_data["severity"]).value < error_event.severity.value:
                error_data["severity"] = error_event.severity.value
        else:
            # Create new error record
            error_data = asdict(error_event)
            error_data["timestamp"] = error_event.timestamp.isoformat()
            error_data["first_seen"] = error_event.timestamp.isoformat()
            error_data["last_seen"] = error_event.timestamp.isoformat()
        
        # Store updated error data
        await self.redis.setex(
            error_key,
            self.error_retention_days * 24 * 3600,
            json.dumps(error_data, default=str)
        )
        
        # Store individual occurrence
        occurrence_data = {
            "timestamp": error_event.timestamp.isoformat(),
            "user_id": error_event.user_id,
            "request_id": error_event.request_id,
            "context": error_event.context
        }
        
        await self.redis.lpush(occurrence_key, json.dumps(occurrence_data, default=str))
        await self.redis.ltrim(occurrence_key, 0, 100)  # Keep last 100 occurrences
        await self.redis.expire(occurrence_key, self.error_retention_days * 24 * 3600)
    
    async def _get_error_events(
        self,
        start_time: datetime,
        end_time: datetime,
        component: Optional[str] = None
    ) -> List[ErrorEvent]:
        """Retrieve error events from Redis within time range."""
        
        # Get all error keys
        error_keys = await self.redis.keys("error:*")
        error_events = []
        
        for key in error_keys:
            error_data = await self.redis.get(key)
            if error_data:
                error_info = json.loads(error_data)
                
                # Parse timestamp
                last_seen = datetime.fromisoformat(error_info["last_seen"])
                
                # Filter by time range
                if start_time <= last_seen <= end_time:
                    # Filter by component if specified
                    if component is None or error_info["component"] == component:
                        error_event = ErrorEvent(**{
                            k: v for k, v in error_info.items()
                            if k in ErrorEvent.__dataclass_fields__
                        })
                        error_events.append(error_event)
        
        return error_events
    
    async def _calculate_error_trends(self, error_events: List[ErrorEvent]) -> Dict[str, Any]:
        """Calculate error trends and patterns."""
        
        if not error_events:
            return {"trend": "stable", "change_percent": 0}
        
        # Group errors by hour
        hourly_counts = {}
        for event in error_events:
            hour = event.last_seen.replace(minute=0, second=0, microsecond=0)
            hourly_counts[hour] = hourly_counts.get(hour, 0) + event.frequency
        
        if len(hourly_counts) < 2:
            return {"trend": "insufficient_data", "change_percent": 0}
        
        # Calculate trend
        hours = sorted(hourly_counts.keys())
        recent_hours = hours[-3:] if len(hours) >= 3 else hours
        earlier_hours = hours[:-3] if len(hours) >= 6 else hours[:-len(recent_hours)]
        
        if not earlier_hours:
            return {"trend": "insufficient_data", "change_percent": 0}
        
        recent_avg = sum(hourly_counts[h] for h in recent_hours) / len(recent_hours)
        earlier_avg = sum(hourly_counts[h] for h in earlier_hours) / len(earlier_hours)
        
        if earlier_avg == 0:
            change_percent = 100 if recent_avg > 0 else 0
        else:
            change_percent = ((recent_avg - earlier_avg) / earlier_avg) * 100
        
        if change_percent > 20:
            trend = "increasing"
        elif change_percent < -20:
            trend = "decreasing"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "change_percent": round(change_percent, 2),
            "recent_avg_per_hour": round(recent_avg, 2),
            "earlier_avg_per_hour": round(earlier_avg, 2)
        }
    
    async def _check_error_thresholds(self, error_event: ErrorEvent):
        """Check if error event exceeds alerting thresholds."""
        
        # Critical errors always alert
        if error_event.severity == ErrorSeverity.CRITICAL:
            await self._create_alert(
                AlertType.ERROR_RATE,
                f"Critical error in {error_event.component}: {error_event.error_message}",
                ErrorSeverity.CRITICAL,
                error_event.component,
                {"error_event": asdict(error_event)}
            )
        
        # Check error rate thresholds
        recent_errors = await self._get_recent_error_count(
            error_event.component,
            minutes=5
        )
        
        if recent_errors >= 10:  # 10 errors in 5 minutes
            await self._create_alert(
                AlertType.ERROR_RATE,
                f"High error rate in {error_event.component}: {recent_errors} errors in 5 minutes",
                ErrorSeverity.HIGH,
                error_event.component,
                {"error_count": recent_errors, "time_window_minutes": 5}
            )
    
    async def _get_recent_error_count(self, component: str, minutes: int) -> int:
        """Get error count for component in recent time window."""
        
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        error_keys = await self.redis.keys("error:*")
        
        count = 0
        for key in error_keys:
            error_data = await self.redis.get(key)
            if error_data:
                error_info = json.loads(error_data)
                if (error_info["component"] == component and
                    datetime.fromisoformat(error_info["last_seen"]) >= cutoff_time):
                    count += error_info.get("frequency", 1)
        
        return count
    
    async def _create_alert(
        self,
        alert_type: AlertType,
        message: str,
        severity: ErrorSeverity,
        component: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Create monitoring alert."""
        
        alert = PerformanceAlert(
            alert_id=f"{alert_type.value}_{component}_{int(time.time())}",
            alert_type=alert_type,
            message=message,
            severity=severity,
            timestamp=datetime.utcnow(),
            threshold_value=0,  # Set based on alert type
            current_value=0,    # Set based on alert type
            component=component,
            context=context
        )
        
        # Store alert
        alert_key = f"alert:{alert.alert_id}"
        await self.redis.setex(
            alert_key,
            7 * 24 * 3600,  # 7 days retention
            json.dumps(asdict(alert), default=str)
        )
        
        # Add to alerts list for the component
        alerts_key = f"alerts:{component}"
        await self.redis.lpush(alerts_key, alert.alert_id)
        await self.redis.ltrim(alerts_key, 0, 100)  # Keep last 100 alerts
        await self.redis.expire(alerts_key, 7 * 24 * 3600)
        
        # Log alert
        logging.getLogger('monitoring').warning(
            f"Alert created: {message}",
            extra={
                'extra_fields': {
                    'alert_type': alert_type.value,
                    'severity': severity.value,
                    'component': component,
                    'alert_id': alert.alert_id
                }
            }
        )


class PerformanceMonitor:
    """Advanced performance monitoring and alerting."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.error_tracker = ErrorTracker(redis_client)
        
    async def track_response_time(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True
    ):
        """Track operation response times."""
        
        # Store in Redis with sliding window
        timestamp = int(time.time())
        window_key = f"response_times:{operation}:{timestamp // 60}"  # 1-minute windows
        
        await self.redis.lpush(window_key, duration_ms)
        await self.redis.expire(window_key, 3600)  # Keep for 1 hour
        
        # Check thresholds
        if duration_ms > 5000:  # 5 seconds
            await self.error_tracker._create_alert(
                AlertType.RESPONSE_TIME,
                f"Slow response time for {operation}: {duration_ms:.2f}ms",
                ErrorSeverity.MEDIUM,
                operation,
                {"duration_ms": duration_ms, "threshold_ms": 5000}
            )
    
    async def get_performance_summary(self, hours: int = 1) -> Dict[str, Any]:
        """Get performance summary for specified time period."""
        
        end_time = int(time.time())
        start_time = end_time - (hours * 3600)
        
        # Get all response time keys in time range
        response_time_data = {}
        
        for timestamp in range(start_time // 60, end_time // 60):
            keys = await self.redis.keys(f"response_times:*:{timestamp}")
            
            for key in keys:
                operation = key.split(':')[1]
                times = await self.redis.lrange(key, 0, -1)
                
                if operation not in response_time_data:
                    response_time_data[operation] = []
                
                response_time_data[operation].extend([float(t) for t in times])
        
        # Calculate statistics
        performance_stats = {}
        for operation, times in response_time_data.items():
            if times:
                performance_stats[operation] = {
                    "count": len(times),
                    "avg_ms": sum(times) / len(times),
                    "min_ms": min(times),
                    "max_ms": max(times),
                    "p95_ms": self._percentile(times, 95),
                    "p99_ms": self._percentile(times, 99)
                }
        
        return {
            "time_period_hours": hours,
            "operations": performance_stats,
            "overall_metrics": self._calculate_overall_metrics(performance_stats)
        }
    
    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile of data."""
        if not data:
            return 0
        
        sorted_data = sorted(data)
        index = int((percentile / 100) * len(sorted_data))
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def _calculate_overall_metrics(self, operation_stats: Dict[str, Dict]) -> Dict[str, Any]:
        """Calculate overall performance metrics."""
        
        if not operation_stats:
            return {}
        
        all_times = []
        total_requests = 0
        
        for stats in operation_stats.values():
            total_requests += stats["count"]
            # Approximate individual times for overall calculations
            all_times.extend([stats["avg_ms"]] * stats["count"])
        
        if not all_times:
            return {}
        
        return {
            "total_requests": total_requests,
            "overall_avg_ms": sum(all_times) / len(all_times),
            "overall_p95_ms": self._percentile(all_times, 95),
            "overall_p99_ms": self._percentile(all_times, 99),
            "slowest_operation": max(
                operation_stats.items(),
                key=lambda x: x[1]["avg_ms"]
            )[0] if operation_stats else None
        }


# Global monitoring instances
error_tracker = ErrorTracker(redis_client)
performance_monitor = PerformanceMonitor(redis_client)


def track_errors(component: str, operation: str):
    """Decorator to automatically track errors."""
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                await error_tracker.track_error(
                    e, component, operation,
                    severity=ErrorSeverity.MEDIUM
                )
                raise
        
        return wrapper
    return decorator