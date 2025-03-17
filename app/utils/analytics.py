"""
API usage analytics and advanced rate limiting with user tiers.
"""

import time
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from collections import defaultdict

from app.services.redis_client import redis_client
from app.utils.metrics import metrics


class UserTier(str, Enum):
    """User subscription tiers with different rate limits."""
    FREE = "free"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class EndpointCategory(str, Enum):
    """Categories of API endpoints for analytics."""
    AUTHENTICATION = "authentication"
    DEVICES = "devices"
    GEOFENCES = "geofences"
    ROUTING = "routing"
    RECOMMENDATIONS = "recommendations"
    ANALYTICS = "analytics"
    MONITORING = "monitoring"


@dataclass
class TierLimits:
    """Rate limits and quotas for user tiers."""
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    max_devices: int
    max_geofences: int
    max_route_waypoints: int
    advanced_features: bool


# Tier configurations
TIER_LIMITS = {
    UserTier.FREE: TierLimits(
        requests_per_minute=60,
        requests_per_hour=1000,
        requests_per_day=10000,
        max_devices=5,
        max_geofences=10,
        max_route_waypoints=10,
        advanced_features=False
    ),
    UserTier.BASIC: TierLimits(
        requests_per_minute=300,
        requests_per_hour=10000,
        requests_per_day=100000,
        max_devices=50,
        max_geofences=100,
        max_route_waypoints=25,
        advanced_features=True
    ),
    UserTier.PROFESSIONAL: TierLimits(
        requests_per_minute=1000,
        requests_per_hour=50000,
        requests_per_day=1000000,
        max_devices=500,
        max_geofences=1000,
        max_route_waypoints=100,
        advanced_features=True
    ),
    UserTier.ENTERPRISE: TierLimits(
        requests_per_minute=5000,
        requests_per_hour=200000,
        requests_per_day=5000000,
        max_devices=10000,
        max_geofences=10000,
        max_route_waypoints=500,
        advanced_features=True
    )
}


class APIAnalytics:
    """Comprehensive API usage analytics."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.retention_days = 90
    
    async def track_request(
        self,
        user_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: float,
        request_size: int = 0,
        response_size: int = 0,
        user_tier: UserTier = UserTier.FREE
    ):
        """Track API request for analytics."""
        
        timestamp = int(time.time())
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        hour_str = datetime.utcnow().strftime('%Y-%m-%d:%H')
        
        # Categorize endpoint
        category = self._categorize_endpoint(endpoint)
        
        # Track multiple metrics in parallel
        await self._track_multiple_metrics(
            user_id, endpoint, method, status_code, response_time_ms,
            request_size, response_size, user_tier, category,
            timestamp, date_str, hour_str
        )
    
    async def _track_multiple_metrics(
        self, user_id: str, endpoint: str, method: str, status_code: int,
        response_time_ms: float, request_size: int, response_size: int,
        user_tier: UserTier, category: EndpointCategory,
        timestamp: int, date_str: str, hour_str: str
    ):
        """Track multiple metrics efficiently using Redis pipeline."""
        
        pipe = self.redis.pipeline()
        
        # User-specific metrics
        user_key_prefix = f"analytics:user:{user_id}"
        
        # Daily request count
        pipe.incr(f"{user_key_prefix}:requests:daily:{date_str}")
        pipe.expire(f"{user_key_prefix}:requests:daily:{date_str}", self.retention_days * 24 * 3600)
        
        # Hourly request count
        pipe.incr(f"{user_key_prefix}:requests:hourly:{hour_str}")
        pipe.expire(f"{user_key_prefix}:requests:hourly:{hour_str}", 7 * 24 * 3600)
        
        # Endpoint usage
        pipe.incr(f"{user_key_prefix}:endpoints:{endpoint}:{date_str}")
        pipe.expire(f"{user_key_prefix}:endpoints:{endpoint}:{date_str}", self.retention_days * 24 * 3600)
        
        # Category usage
        pipe.incr(f"{user_key_prefix}:categories:{category.value}:{date_str}")
        pipe.expire(f"{user_key_prefix}:categories:{category.value}:{date_str}", self.retention_days * 24 * 3600)
        
        # Response times (for percentile calculations)
        pipe.lpush(f"{user_key_prefix}:response_times:{hour_str}", response_time_ms)
        pipe.ltrim(f"{user_key_prefix}:response_times:{hour_str}", 0, 1000)  # Keep last 1000
        pipe.expire(f"{user_key_prefix}:response_times:{hour_str}", 24 * 3600)
        
        # Status codes
        pipe.incr(f"{user_key_prefix}:status:{status_code}:{date_str}")
        pipe.expire(f"{user_key_prefix}:status:{status_code}:{date_str}", self.retention_days * 24 * 3600)
        
        # Data transfer
        pipe.incrby(f"{user_key_prefix}:bytes_in:{date_str}", request_size)
        pipe.incrby(f"{user_key_prefix}:bytes_out:{date_str}", response_size)
        pipe.expire(f"{user_key_prefix}:bytes_in:{date_str}", self.retention_days * 24 * 3600)
        pipe.expire(f"{user_key_prefix}:bytes_out:{date_str}", self.retention_days * 24 * 3600)
        
        # Global metrics
        global_prefix = "analytics:global"
        
        # Global daily counts by tier
        pipe.incr(f"{global_prefix}:tier:{user_tier.value}:{date_str}")
        pipe.expire(f"{global_prefix}:tier:{user_tier.value}:{date_str}", self.retention_days * 24 * 3600)
        
        # Global endpoint popularity
        pipe.incr(f"{global_prefix}:endpoints:{endpoint}:{date_str}")
        pipe.expire(f"{global_prefix}:endpoints:{endpoint}:{date_str}", self.retention_days * 24 * 3600)
        
        # Error tracking
        if status_code >= 400:
            pipe.incr(f"{global_prefix}:errors:{status_code}:{date_str}")
            pipe.expire(f"{global_prefix}:errors:{status_code}:{date_str}", self.retention_days * 24 * 3600)
        
        # Execute all operations
        await pipe.execute()
        
        # Update Prometheus metrics
        metrics.api_key_usage.labels(
            api_key_id=user_id[:8],
            endpoint=self._normalize_endpoint(endpoint)
        ).inc()
    
    async def get_user_analytics(
        self,
        user_id: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get comprehensive analytics for a user."""
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        analytics = {
            "user_id": user_id,
            "time_period_days": days,
            "summary": {},
            "daily_breakdown": {},
            "endpoint_usage": {},
            "category_usage": {},
            "performance": {},
            "errors": {}
        }
        
        # Get daily request counts
        daily_requests = {}
        total_requests = 0
        
        for i in range(days):
            date = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
            key = f"analytics:user:{user_id}:requests:daily:{date}"
            count = await self.redis.get(key)
            daily_count = int(count) if count else 0
            daily_requests[date] = daily_count
            total_requests += daily_count
        
        analytics["summary"]["total_requests"] = total_requests
        analytics["summary"]["avg_requests_per_day"] = total_requests / days if days > 0 else 0
        analytics["daily_breakdown"] = daily_requests
        
        # Get endpoint usage
        endpoint_keys = await self.redis.keys(f"analytics:user:{user_id}:endpoints:*")
        endpoint_usage = {}
        
        for key in endpoint_keys:
            endpoint = key.split(':')[4]  # Extract endpoint from key
            count = await self.redis.get(key)
            if endpoint not in endpoint_usage:
                endpoint_usage[endpoint] = 0
            endpoint_usage[endpoint] += int(count) if count else 0
        
        analytics["endpoint_usage"] = dict(sorted(
            endpoint_usage.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20])  # Top 20 endpoints
        
        # Get category usage
        category_keys = await self.redis.keys(f"analytics:user:{user_id}:categories:*")
        category_usage = {}
        
        for key in category_keys:
            category = key.split(':')[4]
            count = await self.redis.get(key)
            if category not in category_usage:
                category_usage[category] = 0
            category_usage[category] += int(count) if count else 0
        
        analytics["category_usage"] = category_usage
        
        # Get performance data
        response_time_keys = await self.redis.keys(f"analytics:user:{user_id}:response_times:*")
        all_response_times = []
        
        for key in response_time_keys:
            times = await self.redis.lrange(key, 0, -1)
            all_response_times.extend([float(t) for t in times])
        
        if all_response_times:
            all_response_times.sort()
            analytics["performance"] = {
                "avg_response_time_ms": sum(all_response_times) / len(all_response_times),
                "min_response_time_ms": min(all_response_times),
                "max_response_time_ms": max(all_response_times),
                "p50_response_time_ms": self._percentile(all_response_times, 50),
                "p95_response_time_ms": self._percentile(all_response_times, 95),
                "p99_response_time_ms": self._percentile(all_response_times, 99)
            }
        
        # Get error statistics
        error_keys = await self.redis.keys(f"analytics:user:{user_id}:status:*")
        error_counts = {}
        success_count = 0
        
        for key in error_keys:
            status_code = int(key.split(':')[4])
            count = await self.redis.get(key)
            count = int(count) if count else 0
            
            if status_code >= 400:
                error_counts[str(status_code)] = error_counts.get(str(status_code), 0) + count
            else:
                success_count += count
        
        total_counted = success_count + sum(error_counts.values())
        analytics["errors"] = {
            "error_counts": error_counts,
            "error_rate": sum(error_counts.values()) / total_counted if total_counted > 0 else 0,
            "success_rate": success_count / total_counted if total_counted > 0 else 0
        }
        
        return analytics
    
    async def get_global_analytics(self, days: int = 7) -> Dict[str, Any]:
        """Get global platform analytics."""
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        analytics = {
            "time_period_days": days,
            "tier_distribution": {},
            "popular_endpoints": {},
            "error_summary": {},
            "usage_trends": {}
        }
        
        # Get tier distribution
        tier_data = {}
        for tier in UserTier:
            tier_total = 0
            for i in range(days):
                date = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
                key = f"analytics:global:tier:{tier.value}:{date}"
                count = await self.redis.get(key)
                tier_total += int(count) if count else 0
            tier_data[tier.value] = tier_total
        
        analytics["tier_distribution"] = tier_data
        
        # Get popular endpoints
        endpoint_keys = await self.redis.keys("analytics:global:endpoints:*")
        endpoint_popularity = {}
        
        for key in endpoint_keys:
            endpoint = key.split(':')[3]
            count = await self.redis.get(key)
            if endpoint not in endpoint_popularity:
                endpoint_popularity[endpoint] = 0
            endpoint_popularity[endpoint] += int(count) if count else 0
        
        analytics["popular_endpoints"] = dict(sorted(
            endpoint_popularity.items(),
            key=lambda x: x[1],
            reverse=True
        )[:15])
        
        # Get error summary
        error_keys = await self.redis.keys("analytics:global:errors:*")
        error_summary = {}
        
        for key in error_keys:
            status_code = key.split(':')[3]
            count = await self.redis.get(key)
            if status_code not in error_summary:
                error_summary[status_code] = 0
            error_summary[status_code] += int(count) if count else 0
        
        analytics["error_summary"] = error_summary
        
        return analytics
    
    async def check_user_limits(
        self,
        user_id: str,
        user_tier: UserTier,
        resource_type: str,
        current_count: int
    ) -> Dict[str, Any]:
        """Check if user is within tier limits for resources."""
        
        limits = TIER_LIMITS[user_tier]
        
        # Check daily request limit
        today = datetime.utcnow().strftime('%Y-%m-%d')
        daily_requests_key = f"analytics:user:{user_id}:requests:daily:{today}"
        daily_requests = await self.redis.get(daily_requests_key)
        daily_requests = int(daily_requests) if daily_requests else 0
        
        # Check specific resource limits
        resource_limits = {
            "devices": limits.max_devices,
            "geofences": limits.max_geofences,
            "route_waypoints": limits.max_route_waypoints
        }
        
        result = {
            "within_limits": True,
            "daily_requests": {
                "current": daily_requests,
                "limit": limits.requests_per_day,
                "remaining": max(0, limits.requests_per_day - daily_requests)
            },
            "resource_limits": {}
        }
        
        # Check daily request limit
        if daily_requests >= limits.requests_per_day:
            result["within_limits"] = False
            result["exceeded_limits"] = ["daily_requests"]
        
        # Check specific resource limit
        if resource_type in resource_limits:
            resource_limit = resource_limits[resource_type]
            result["resource_limits"][resource_type] = {
                "current": current_count,
                "limit": resource_limit,
                "remaining": max(0, resource_limit - current_count)
            }
            
            if current_count >= resource_limit:
                result["within_limits"] = False
                result["exceeded_limits"] = result.get("exceeded_limits", []) + [resource_type]
        
        return result
    
    def _categorize_endpoint(self, endpoint: str) -> EndpointCategory:
        """Categorize endpoint for analytics."""
        
        if "/auth" in endpoint:
            return EndpointCategory.AUTHENTICATION
        elif "/devices" in endpoint:
            return EndpointCategory.DEVICES
        elif "/geofences" in endpoint:
            return EndpointCategory.GEOFENCES
        elif "/routes" in endpoint:
            return EndpointCategory.ROUTING
        elif "/recommendations" in endpoint:
            return EndpointCategory.RECOMMENDATIONS
        elif "/analytics" in endpoint or "/monitoring" in endpoint:
            return EndpointCategory.MONITORING
        else:
            return EndpointCategory.ANALYTICS
    
    def _normalize_endpoint(self, endpoint: str) -> str:
        """Normalize endpoint for metrics (remove IDs)."""
        import re
        
        # Replace UUIDs and numeric IDs with placeholders
        endpoint = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{id}', endpoint)
        endpoint = re.sub(r'/\d+(?=/|$)', '/{id}', endpoint)
        
        return endpoint
    
    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile of data."""
        if not data:
            return 0
        
        sorted_data = sorted(data)
        index = int((percentile / 100) * len(sorted_data))
        return sorted_data[min(index, len(sorted_data) - 1)]


class EnhancedRateLimiter:
    """Enhanced rate limiter with tier-based limits."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.analytics = APIAnalytics(redis_client)
    
    async def check_rate_limit(
        self,
        user_id: str,
        user_tier: UserTier,
        endpoint: str
    ) -> Dict[str, Any]:
        """Check rate limit based on user tier."""
        
        limits = TIER_LIMITS[user_tier]
        now = int(time.time())
        
        # Check different time windows
        minute_key = f"rate_limit:{user_id}:minute:{now // 60}"
        hour_key = f"rate_limit:{user_id}:hour:{now // 3600}"
        day_key = f"rate_limit:{user_id}:day:{now // (24 * 3600)}"
        
        # Get current counts
        minute_count = await self.redis.get(minute_key)
        hour_count = await self.redis.get(hour_key)
        day_count = await self.redis.get(day_key)
        
        minute_count = int(minute_count) if minute_count else 0
        hour_count = int(hour_count) if hour_count else 0
        day_count = int(day_count) if day_count else 0
        
        # Check limits
        rate_limit_info = {
            "allowed": True,
            "limits": {
                "minute": {"current": minute_count, "limit": limits.requests_per_minute},
                "hour": {"current": hour_count, "limit": limits.requests_per_hour},
                "day": {"current": day_count, "limit": limits.requests_per_day}
            },
            "tier": user_tier.value
        }
        
        # Check if any limit is exceeded
        if minute_count >= limits.requests_per_minute:
            rate_limit_info["allowed"] = False
            rate_limit_info["exceeded_limit"] = "minute"
            rate_limit_info["retry_after"] = 60 - (now % 60)
        elif hour_count >= limits.requests_per_hour:
            rate_limit_info["allowed"] = False
            rate_limit_info["exceeded_limit"] = "hour"
            rate_limit_info["retry_after"] = 3600 - (now % 3600)
        elif day_count >= limits.requests_per_day:
            rate_limit_info["allowed"] = False
            rate_limit_info["exceeded_limit"] = "day"
            rate_limit_info["retry_after"] = (24 * 3600) - (now % (24 * 3600))
        
        # If allowed, increment counters
        if rate_limit_info["allowed"]:
            pipe = self.redis.pipeline()
            pipe.incr(minute_key)
            pipe.expire(minute_key, 60)
            pipe.incr(hour_key)
            pipe.expire(hour_key, 3600)
            pipe.incr(day_key)
            pipe.expire(day_key, 24 * 3600)
            await pipe.execute()
        
        return rate_limit_info


# Global analytics instance
api_analytics = APIAnalytics(redis_client)
enhanced_rate_limiter = EnhancedRateLimiter(redis_client)