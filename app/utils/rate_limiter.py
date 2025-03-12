import asyncio
import time
from typing import Dict, Optional
from collections import defaultdict
from fastapi import Request, HTTPException, status
from app.services.redis_client import redis_client
from app.config import settings
import json


class RateLimiter:
    def __init__(self, requests_per_minute: int = None):
        self.requests_per_minute = requests_per_minute or settings.rate_limit_per_minute
        self.window_size = 60  # 1 minute in seconds
        
    async def is_allowed(self, key: str) -> tuple[bool, dict]:
        """
        Check if request is allowed based on rate limit
        Returns (is_allowed, info_dict)
        """
        now = int(time.time())
        window_start = now - self.window_size
        
        # Use Redis sliding window log
        pipe = redis_client.redis.pipeline()
        
        # Remove old entries
        await redis_client.redis.zremrangebyscore(key, 0, window_start)
        
        # Count current requests in window
        current_requests = await redis_client.redis.zcard(key)
        
        if current_requests >= self.requests_per_minute:
            # Get the oldest request time to calculate reset time
            oldest_request = await redis_client.redis.zrange(key, 0, 0, withscores=True)
            reset_time = int(oldest_request[0][1]) + self.window_size if oldest_request else now + self.window_size
            
            return False, {
                "limit": self.requests_per_minute,
                "remaining": 0,
                "reset": reset_time,
                "retry_after": reset_time - now
            }
        
        # Add current request
        await redis_client.redis.zadd(key, {str(now): now})
        
        # Set expiry for the key
        await redis_client.redis.expire(key, self.window_size + 1)
        
        remaining = max(0, self.requests_per_minute - current_requests - 1)
        
        return True, {
            "limit": self.requests_per_minute,
            "remaining": remaining,
            "reset": now + self.window_size,
            "retry_after": 0
        }


class InMemoryRateLimiter:
    """Fallback rate limiter when Redis is not available"""
    
    def __init__(self, requests_per_minute: int = None):
        self.requests_per_minute = requests_per_minute or settings.rate_limit_per_minute
        self.window_size = 60
        self.requests: Dict[str, list] = defaultdict(list)
        self._cleanup_interval = 60
        self._last_cleanup = time.time()
    
    def _cleanup_old_requests(self):
        """Clean up old request records"""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
            
        cutoff = now - self.window_size
        for key in list(self.requests.keys()):
            self.requests[key] = [t for t in self.requests[key] if t > cutoff]
            if not self.requests[key]:
                del self.requests[key]
        
        self._last_cleanup = now
    
    async def is_allowed(self, key: str) -> tuple[bool, dict]:
        """Check if request is allowed"""
        self._cleanup_old_requests()
        
        now = time.time()
        window_start = now - self.window_size
        
        # Filter requests within current window
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        current_requests = len(self.requests[key])
        
        if current_requests >= self.requests_per_minute:
            oldest_request = min(self.requests[key]) if self.requests[key] else now
            reset_time = oldest_request + self.window_size
            
            return False, {
                "limit": self.requests_per_minute,
                "remaining": 0,
                "reset": int(reset_time),
                "retry_after": int(reset_time - now)
            }
        
        # Add current request
        self.requests[key].append(now)
        remaining = max(0, self.requests_per_minute - current_requests - 1)
        
        return True, {
            "limit": self.requests_per_minute,
            "remaining": remaining,
            "reset": int(now + self.window_size),
            "retry_after": 0
        }


# Global rate limiter instances
default_rate_limiter = RateLimiter()
fallback_rate_limiter = InMemoryRateLimiter()


async def get_client_identifier(request: Request) -> str:
    """Extract client identifier for rate limiting"""
    # Try to get user ID from auth if available
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    
    # Try to get API key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"api_key:{api_key[:8]}"  # Use first 8 chars for privacy
    
    # Fall back to IP address
    client_ip = request.client.host
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    return f"ip:{client_ip}"


async def check_rate_limit(request: Request, requests_per_minute: int = None) -> dict:
    """Check rate limit for request"""
    identifier = await get_client_identifier(request)
    rate_limiter = RateLimiter(requests_per_minute) if requests_per_minute else default_rate_limiter
    
    try:
        # Try Redis-based rate limiting first
        if redis_client.redis:
            is_allowed, info = await rate_limiter.is_allowed(f"rate_limit:{identifier}")
        else:
            # Fall back to in-memory rate limiting
            is_allowed, info = await fallback_rate_limiter.is_allowed(f"rate_limit:{identifier}")
    except Exception:
        # If rate limiting fails, allow the request but log the error
        is_allowed, info = True, {
            "limit": rate_limiter.requests_per_minute,
            "remaining": rate_limiter.requests_per_minute,
            "reset": int(time.time() + 60),
            "retry_after": 0
        }
    
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded",
                "limit": info["limit"],
                "retry_after": info["retry_after"]
            },
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": str(info["remaining"]),
                "X-RateLimit-Reset": str(info["reset"]),
                "Retry-After": str(info["retry_after"])
            }
        )
    
    return info