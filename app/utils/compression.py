"""
Response compression and caching utilities.
"""

import gzip
import brotli
import json
import hashlib
from typing import Any, Dict, Optional, Union
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse
import asyncio
import time

from app.services.redis_client import redis_client


class CompressionMiddleware(BaseHTTPMiddleware):
    """Middleware for response compression based on client capabilities."""
    
    def __init__(self, app, minimum_size: int = 1024):
        super().__init__(app)
        self.minimum_size = minimum_size
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Skip compression for certain content types
        if self._should_skip_compression(response):
            return response
        
        # Get response body
        if hasattr(response, 'body'):
            body = response.body
        else:
            # For streaming responses, we can't compress
            return response
        
        # Only compress if body is large enough
        if len(body) < self.minimum_size:
            return response
        
        # Determine best compression method
        accept_encoding = request.headers.get('accept-encoding', '')
        
        if 'br' in accept_encoding and len(body) > 2048:
            # Use Brotli for larger responses (better compression)
            compressed_body = brotli.compress(body, quality=6)
            encoding = 'br'
        elif 'gzip' in accept_encoding:
            # Use gzip for general compression
            compressed_body = gzip.compress(body, compresslevel=6)
            encoding = 'gzip'
        else:
            # No compression supported
            return response
        
        # Only use compression if it actually reduces size
        if len(compressed_body) >= len(body):
            return response
        
        # Create compressed response
        headers = dict(response.headers)
        headers['content-encoding'] = encoding
        headers['content-length'] = str(len(compressed_body))
        headers['vary'] = 'Accept-Encoding'
        
        return Response(
            content=compressed_body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type
        )
    
    def _should_skip_compression(self, response) -> bool:
        """Determine if response should skip compression."""
        content_type = getattr(response, 'media_type', '')
        
        # Skip already compressed content
        skip_types = [
            'image/', 'video/', 'audio/',
            'application/zip', 'application/gzip',
            'application/x-tar', 'application/pdf'
        ]
        
        return any(content_type.startswith(skip_type) for skip_type in skip_types)


class ResponseCacheManager:
    """Advanced response caching with intelligent invalidation."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.default_ttl = 300  # 5 minutes
        self.max_cache_size = 10 * 1024 * 1024  # 10MB max per cache entry
    
    def generate_cache_key(
        self,
        request: Request,
        user_id: Optional[str] = None,
        additional_params: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate consistent cache key for request."""
        
        # Include method, path, and query parameters
        key_parts = [
            request.method,
            request.url.path,
            str(sorted(request.query_params.items()))
        ]
        
        # Include user context if available
        if user_id:
            key_parts.append(f"user:{user_id}")
        
        # Include additional parameters
        if additional_params:
            key_parts.append(str(sorted(additional_params.items())))
        
        # Create hash for consistent key length
        key_string = "|".join(key_parts)
        return f"response_cache:{hashlib.md5(key_string.encode()).hexdigest()}"
    
    async def get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response data."""
        try:
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception:
            pass
        return None
    
    async def cache_response(
        self,
        cache_key: str,
        response_data: Any,
        ttl: Optional[int] = None,
        tags: Optional[list] = None
    ):
        """Cache response data with optional tags for invalidation."""
        try:
            # Serialize response data
            serialized_data = json.dumps({
                "data": response_data,
                "timestamp": time.time(),
                "tags": tags or []
            }, default=str)
            
            # Check size limit
            if len(serialized_data) > self.max_cache_size:
                return False
            
            # Cache with TTL
            await self.redis.setex(
                cache_key,
                ttl or self.default_ttl,
                serialized_data
            )
            
            # Store cache key by tags for invalidation
            if tags:
                for tag in tags:
                    await self.redis.sadd(f"cache_tag:{tag}", cache_key)
                    await self.redis.expire(f"cache_tag:{tag}", (ttl or self.default_ttl) + 60)
            
            return True
            
        except Exception:
            return False
    
    async def invalidate_by_tags(self, tags: list):
        """Invalidate all cached responses with given tags."""
        try:
            cache_keys = set()
            
            # Collect all cache keys for these tags
            for tag in tags:
                tag_keys = await self.redis.smembers(f"cache_tag:{tag}")
                cache_keys.update(tag_keys)
            
            # Delete cache entries
            if cache_keys:
                await self.redis.delete(*cache_keys)
            
            # Clean up tag sets
            for tag in tags:
                await self.redis.delete(f"cache_tag:{tag}")
                
        except Exception:
            pass
    
    async def invalidate_pattern(self, pattern: str):
        """Invalidate cached responses by key pattern."""
        try:
            keys = await self.redis.keys(f"response_cache:*{pattern}*")
            if keys:
                await self.redis.delete(*keys)
        except Exception:
            pass


class CacheableResponse(JSONResponse):
    """JSON response with caching metadata."""
    
    def __init__(
        self,
        content: Any,
        cache_ttl: Optional[int] = None,
        cache_tags: Optional[list] = None,
        **kwargs
    ):
        super().__init__(content, **kwargs)
        self.cache_ttl = cache_ttl
        self.cache_tags = cache_tags or []


def cache_response(
    ttl: int = 300,
    tags: Optional[list] = None,
    key_generator: Optional[callable] = None
):
    """Decorator for caching API responses."""
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract request and user info from function args
            request = None
            user_id = None
            
            for arg in args + tuple(kwargs.values()):
                if isinstance(arg, Request):
                    request = arg
                elif hasattr(arg, 'id'):  # User object
                    user_id = str(arg.id)
            
            if not request:
                # Can't cache without request context
                return await func(*args, **kwargs)
            
            cache_manager = ResponseCacheManager(redis_client)
            
            # Generate cache key
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                cache_key = cache_manager.generate_cache_key(request, user_id)
            
            # Try to get from cache
            cached_response = await cache_manager.get_cached_response(cache_key)
            if cached_response:
                return cached_response["data"]
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            
            # Cache the result
            await cache_manager.cache_response(
                cache_key,
                result if not isinstance(result, Response) else result.body.decode(),
                ttl,
                tags
            )
            
            return result
        
        return wrapper
    return decorator


class SmartCacheInvalidator:
    """Intelligent cache invalidation based on data changes."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.cache_manager = ResponseCacheManager(redis_client)
    
    async def invalidate_user_caches(self, user_id: str):
        """Invalidate all caches for a specific user."""
        await self.cache_manager.invalidate_by_tags([f"user:{user_id}"])
    
    async def invalidate_device_caches(self, user_id: str, device_id: str):
        """Invalidate device-related caches."""
        tags = [
            f"user:{user_id}",
            f"device:{device_id}",
            "device_list",
            "device_stats"
        ]
        await self.cache_manager.invalidate_by_tags(tags)
    
    async def invalidate_geofence_caches(self, user_id: str, geofence_id: str):
        """Invalidate geofence-related caches."""
        tags = [
            f"user:{user_id}",
            f"geofence:{geofence_id}",
            "geofence_list",
            "spatial_search"
        ]
        await self.cache_manager.invalidate_by_tags(tags)
    
    async def invalidate_location_caches(self, user_id: str, latitude: float, longitude: float):
        """Invalidate location-based caches in an area."""
        # Invalidate caches for approximate location (rounded to reduce cache spread)
        lat_rounded = round(latitude, 3)  # ~100m precision
        lon_rounded = round(longitude, 3)
        
        tags = [
            f"user:{user_id}",
            f"location:{lat_rounded}:{lon_rounded}",
            "nearby_search",
            "recommendations"
        ]
        await self.cache_manager.invalidate_by_tags(tags)
    
    async def invalidate_route_caches(self, user_id: str):
        """Invalidate route-related caches."""
        tags = [
            f"user:{user_id}",
            "routes",
            "optimization"
        ]
        await self.cache_manager.invalidate_by_tags(tags)


class PerformanceOptimizer:
    """Response optimization utilities."""
    
    @staticmethod
    def optimize_json_response(data: Any) -> Dict[str, Any]:
        """Optimize JSON response for faster serialization."""
        
        if isinstance(data, list):
            # For large lists, consider pagination
            if len(data) > 1000:
                return {
                    "data": data[:1000],
                    "total": len(data),
                    "truncated": True,
                    "message": "Results truncated for performance. Use pagination for full results."
                }
        
        return data
    
    @staticmethod
    def create_etag(content: Any) -> str:
        """Create ETag for response caching."""
        content_str = json.dumps(content, sort_keys=True, default=str)
        return hashlib.md5(content_str.encode()).hexdigest()
    
    @staticmethod
    def should_return_304(request: Request, etag: str) -> bool:
        """Check if we should return 304 Not Modified."""
        if_none_match = request.headers.get('if-none-match')
        return if_none_match == etag


# Global instances
cache_manager = ResponseCacheManager(redis_client)
cache_invalidator = SmartCacheInvalidator(redis_client)
performance_optimizer = PerformanceOptimizer()