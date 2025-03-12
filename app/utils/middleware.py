from fastapi import Request, Response
from fastapi.responses import JSONResponse
import time
from app.utils.rate_limiter import check_rate_limit
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    def __init__(self, app, requests_per_minute: int = None):
        self.app = app
        self.requests_per_minute = requests_per_minute or settings.rate_limit_per_minute
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        
        # Skip rate limiting for certain paths
        path = request.url.path
        if path in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            await self.app(scope, receive, send)
            return
        
        try:
            # Check rate limit
            rate_limit_info = await check_rate_limit(request, self.requests_per_minute)
            
            # Add rate limit info to request state
            request.state.rate_limit_info = rate_limit_info
            
        except Exception as e:
            # If it's a rate limit exception, send appropriate response
            if hasattr(e, 'status_code') and e.status_code == 429:
                response = JSONResponse(
                    status_code=429,
                    content=e.detail,
                    headers=e.headers if hasattr(e, 'headers') else {}
                )
                await response(scope, receive, send)
                return
            
            # For other exceptions, log and continue
            logger.warning(f"Rate limiting error: {e}")
        
        await self.app(scope, receive, send)


class LoggingMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        start_time = time.time()
        
        # Capture response
        response_body = b""
        status_code = 200
        
        async def send_wrapper(message):
            nonlocal response_body, status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                response_body += message.get("body", b"")
            await send(message)
        
        await self.app(scope, receive, send_wrapper)
        
        # Log request
        process_time = time.time() - start_time
        logger.info(
            f"{request.method} {request.url.path} - "
            f"{status_code} - {process_time:.3f}s - "
            f"{request.client.host if request.client else 'unknown'}"
        )


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                
                # Add security headers
                security_headers = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"x-xss-protection": b"1; mode=block",
                    b"strict-transport-security": b"max-age=31536000; includeSubDomains",
                    b"referrer-policy": b"strict-origin-when-cross-origin",
                }
                
                headers.update(security_headers)
                message["headers"] = list(headers.items())
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)