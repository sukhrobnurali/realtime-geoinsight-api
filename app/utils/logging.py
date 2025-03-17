"""
Structured logging with correlation IDs and performance tracking.
"""

import logging
import json
import uuid
import time
import traceback
from typing import Dict, Any, Optional, Union
from contextvars import ContextVar
from functools import wraps
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio

# Context variables for request tracking
request_id_context: ContextVar[str] = ContextVar('request_id', default='')
user_id_context: ContextVar[str] = ContextVar('user_id', default='')
operation_context: ContextVar[str] = ContextVar('operation', default='')


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Base log structure
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add request context if available
        request_id = request_id_context.get('')
        if request_id:
            log_entry['request_id'] = request_id
        
        user_id = user_id_context.get('')
        if user_id:
            log_entry['user_id'] = user_id
        
        operation = operation_context.get('')
        if operation:
            log_entry['operation'] = operation
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add custom fields from extra
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        
        # Add performance metrics if available
        if hasattr(record, 'duration'):
            log_entry['duration_ms'] = record.duration
        
        if hasattr(record, 'query_count'):
            log_entry['query_count'] = record.query_count
        
        # Add geospatial specific fields
        if hasattr(record, 'latitude'):
            log_entry['latitude'] = record.latitude
        
        if hasattr(record, 'longitude'):
            log_entry['longitude'] = record.longitude
        
        if hasattr(record, 'device_id'):
            log_entry['device_id'] = record.device_id
        
        if hasattr(record, 'geofence_id'):
            log_entry['geofence_id'] = record.geofence_id
        
        return json.dumps(log_entry, default=str)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging with correlation IDs."""
    
    async def dispatch(self, request: Request, call_next):
        # Generate request ID
        request_id = str(uuid.uuid4())
        request_id_context.set(request_id)
        
        # Extract user ID from JWT or API key if available
        user_id = await self._extract_user_id(request)
        if user_id:
            user_id_context.set(user_id)
        
        start_time = time.time()
        
        # Log request
        logger = logging.getLogger('api.request')
        logger.info(
            f"{request.method} {request.url.path}",
            extra={
                'extra_fields': {
                    'method': request.method,
                    'path': request.url.path,
                    'query_params': dict(request.query_params),
                    'client_ip': request.client.host if request.client else None,
                    'user_agent': request.headers.get('user-agent'),
                    'content_length': request.headers.get('content-length', '0')
                }
            }
        )
        
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            
            # Log response
            logger.info(
                f"Response {response.status_code}",
                extra={
                    'extra_fields': {
                        'status_code': response.status_code,
                        'response_size': len(response.body) if hasattr(response, 'body') else 0
                    },
                    'duration': duration_ms
                }
            )
            
            # Add request ID to response headers
            response.headers['X-Request-ID'] = request_id
            
            return response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            # Log error
            logger.error(
                f"Request failed: {str(e)}",
                exc_info=True,
                extra={
                    'extra_fields': {
                        'error_type': type(e).__name__
                    },
                    'duration': duration_ms
                }
            )
            
            raise
        finally:
            # Clean up context
            request_id_context.set('')
            user_id_context.set('')
            operation_context.set('')
    
    async def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request context."""
        try:
            # Try to extract from Authorization header
            auth_header = request.headers.get('authorization')
            if auth_header and auth_header.startswith('Bearer '):
                # In a real implementation, decode JWT here
                # For now, return a placeholder
                return 'extracted_user_id'
            
            # Try to extract from API key
            api_key = request.headers.get('x-api-key')
            if api_key:
                # In a real implementation, look up user by API key
                return 'api_key_user_id'
                
        except Exception:
            pass
        
        return None


class GeospatialLogger:
    """Specialized logger for geospatial operations."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def log_device_update(
        self,
        device_id: str,
        user_id: str,
        latitude: float,
        longitude: float,
        operation: str = "location_update"
    ):
        """Log device location update."""
        operation_context.set(operation)
        
        self.logger.info(
            f"Device location updated: {device_id}",
            extra={
                'extra_fields': {
                    'device_id': device_id,
                    'user_id': user_id,
                    'latitude': latitude,
                    'longitude': longitude,
                    'operation_type': operation
                }
            }
        )
    
    def log_geofence_event(
        self,
        device_id: str,
        geofence_id: str,
        event_type: str,
        latitude: float,
        longitude: float
    ):
        """Log geofence entry/exit events."""
        operation_context.set(f"geofence_{event_type}")
        
        self.logger.info(
            f"Geofence {event_type}: device {device_id}",
            extra={
                'extra_fields': {
                    'device_id': device_id,
                    'geofence_id': geofence_id,
                    'event_type': event_type,
                    'latitude': latitude,
                    'longitude': longitude
                }
            }
        )
    
    def log_route_optimization(
        self,
        user_id: str,
        waypoint_count: int,
        algorithm: str,
        duration_ms: float,
        optimization_savings: float
    ):
        """Log route optimization operations."""
        operation_context.set("route_optimization")
        
        self.logger.info(
            f"Route optimized: {waypoint_count} waypoints",
            extra={
                'extra_fields': {
                    'user_id': user_id,
                    'waypoint_count': waypoint_count,
                    'algorithm': algorithm,
                    'optimization_savings_percent': optimization_savings
                },
                'duration': duration_ms
            }
        )
    
    def log_recommendation_request(
        self,
        user_id: str,
        recommendation_type: str,
        latitude: float,
        longitude: float,
        results_count: int,
        duration_ms: float
    ):
        """Log recommendation requests."""
        operation_context.set("recommendation")
        
        self.logger.info(
            f"Recommendations served: {results_count} results",
            extra={
                'extra_fields': {
                    'user_id': user_id,
                    'recommendation_type': recommendation_type,
                    'latitude': latitude,
                    'longitude': longitude,
                    'results_count': results_count
                },
                'duration': duration_ms
            }
        )
    
    def log_spatial_query(
        self,
        operation: str,
        query_type: str,
        duration_ms: float,
        result_count: int,
        user_id: Optional[str] = None
    ):
        """Log spatial database queries."""
        operation_context.set(f"spatial_{operation}")
        
        self.logger.info(
            f"Spatial query: {query_type}",
            extra={
                'extra_fields': {
                    'operation': operation,
                    'query_type': query_type,
                    'result_count': result_count,
                    'user_id': user_id
                },
                'duration': duration_ms
            }
        )
    
    def log_error(
        self,
        error: Exception,
        operation: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log errors with full context."""
        operation_context.set(operation)
        
        extra_fields = {
            'operation': operation,
            'error_type': type(error).__name__,
            'error_message': str(error)
        }
        
        if context:
            extra_fields.update(context)
        
        self.logger.error(
            f"Operation failed: {operation}",
            exc_info=True,
            extra={'extra_fields': extra_fields}
        )
    
    def log_performance_warning(
        self,
        operation: str,
        duration_ms: float,
        threshold_ms: float,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log performance warnings for slow operations."""
        operation_context.set(operation)
        
        extra_fields = {
            'operation': operation,
            'duration_ms': duration_ms,
            'threshold_ms': threshold_ms,
            'performance_issue': True
        }
        
        if context:
            extra_fields.update(context)
        
        self.logger.warning(
            f"Slow operation detected: {operation} took {duration_ms:.2f}ms",
            extra={'extra_fields': extra_fields}
        )


def log_operation(operation_name: str, log_args: bool = False):
    """Decorator to automatically log function operations."""
    
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = GeospatialLogger(f"{func.__module__}.{func.__name__}")
            operation_context.set(operation_name)
            
            start_time = time.time()
            
            # Log function entry
            extra_fields = {'operation': operation_name}
            if log_args:
                extra_fields['function_args'] = str(args)
                extra_fields['function_kwargs'] = str(kwargs)
            
            logger.logger.debug(
                f"Starting operation: {operation_name}",
                extra={'extra_fields': extra_fields}
            )
            
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                # Log success
                logger.logger.info(
                    f"Operation completed: {operation_name}",
                    extra={
                        'extra_fields': {
                            'operation': operation_name,
                            'success': True
                        },
                        'duration': duration_ms
                    }
                )
                
                # Log performance warning if slow
                if duration_ms > 5000:  # 5 seconds threshold
                    logger.log_performance_warning(
                        operation_name,
                        duration_ms,
                        5000
                    )
                
                return result
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                
                logger.log_error(e, operation_name, {
                    'duration_ms': duration_ms,
                    'function_args': str(args) if log_args else None,
                    'function_kwargs': str(kwargs) if log_args else None
                })
                
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = GeospatialLogger(f"{func.__module__}.{func.__name__}")
            operation_context.set(operation_name)
            
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                logger.logger.info(
                    f"Operation completed: {operation_name}",
                    extra={
                        'extra_fields': {
                            'operation': operation_name,
                            'success': True
                        },
                        'duration': duration_ms
                    }
                )
                
                return result
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.log_error(e, operation_name, {'duration_ms': duration_ms})
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "structured",
    log_file: Optional[str] = None
):
    """Configure application logging."""
    
    # Set log level
    level = getattr(logging, log_level.upper())
    
    # Create formatter
    if log_format == "structured":
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Set specific logger levels
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    
    # Create specialized loggers
    api_logger = logging.getLogger('api')
    api_logger.setLevel(level)
    
    db_logger = logging.getLogger('database')
    db_logger.setLevel(level)
    
    spatial_logger = logging.getLogger('spatial')
    spatial_logger.setLevel(level)


# Global logger instances
geo_logger = GeospatialLogger('geospatial')
api_logger = GeospatialLogger('api')
db_logger = GeospatialLogger('database')