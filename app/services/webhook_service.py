import asyncio
import json
import httpx
from typing import Dict, List, Optional
from datetime import datetime
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.schemas.geofence import GeofenceEvent, WebhookConfig
from app.services.redis_client import redis_client
from app.celery_app import celery_app
import logging

logger = logging.getLogger(__name__)


class WebhookService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.max_retries = 3
        self.retry_delays = [1, 5, 15]  # seconds
    
    async def send_webhook(
        self, 
        webhook_config: WebhookConfig, 
        event: GeofenceEvent,
        retry_count: int = 0
    ) -> bool:
        """Send webhook notification for geofence event"""
        
        if event.event_type not in webhook_config.events:
            return True  # Skip if event type not configured
        
        payload = {
            "event_type": event.event_type,
            "device_id": str(event.device_id),
            "geofence_id": str(event.geofence_id),
            "location": {
                "latitude": event.location.lat,
                "longitude": event.location.lon
            },
            "timestamp": event.timestamp.isoformat(),
            "metadata": event.metadata
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "GeoInsight-API/1.0",
            **webhook_config.headers
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    webhook_config.url,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code in [200, 201, 202, 204]:
                    logger.info(f"Webhook sent successfully to {webhook_config.url}")
                    return True
                else:
                    logger.warning(
                        f"Webhook failed with status {response.status_code}: {response.text}"
                    )
                    return await self._handle_retry(webhook_config, event, retry_count)
                    
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.error(f"Webhook request failed: {e}")
            return await self._handle_retry(webhook_config, event, retry_count)
        except Exception as e:
            logger.error(f"Unexpected error sending webhook: {e}")
            return False
    
    async def _handle_retry(
        self, 
        webhook_config: WebhookConfig, 
        event: GeofenceEvent, 
        retry_count: int
    ) -> bool:
        """Handle webhook retry logic"""
        if retry_count < self.max_retries:
            delay = self.retry_delays[min(retry_count, len(self.retry_delays) - 1)]
            
            # Schedule retry using Celery
            send_webhook_retry.apply_async(
                args=[webhook_config.dict(), event.dict(), retry_count + 1],
                countdown=delay
            )
            return True
        else:
            logger.error(f"Webhook to {webhook_config.url} failed after {self.max_retries} retries")
            return False
    
    async def get_webhook_configs_for_geofence(self, geofence_id: uuid.UUID) -> List[WebhookConfig]:
        """Get webhook configurations for a specific geofence"""
        # In a real implementation, you'd store webhook configs in the database
        # For now, return a mock configuration
        return []
    
    async def register_webhook(
        self, 
        user_id: uuid.UUID, 
        geofence_id: uuid.UUID, 
        webhook_config: WebhookConfig
    ) -> bool:
        """Register a webhook for a geofence"""
        # Store webhook configuration in Redis for quick access
        webhook_key = f"webhook:{user_id}:{geofence_id}"
        webhook_data = webhook_config.dict()
        
        try:
            await redis_client.set(
                webhook_key,
                json.dumps(webhook_data),
                expire=86400 * 30  # 30 days
            )
            return True
        except Exception as e:
            logger.error(f"Error registering webhook: {e}")
            return False
    
    async def get_webhooks_for_geofence(
        self, 
        user_id: uuid.UUID, 
        geofence_id: uuid.UUID
    ) -> Optional[WebhookConfig]:
        """Get webhook configuration for a geofence"""
        webhook_key = f"webhook:{user_id}:{geofence_id}"
        
        try:
            webhook_data = await redis_client.get(webhook_key)
            if webhook_data:
                data = json.loads(webhook_data)
                return WebhookConfig(**data)
        except Exception as e:
            logger.error(f"Error getting webhook config: {e}")
        
        return None
    
    async def remove_webhook(self, user_id: uuid.UUID, geofence_id: uuid.UUID) -> bool:
        """Remove webhook configuration for a geofence"""
        webhook_key = f"webhook:{user_id}:{geofence_id}"
        
        try:
            await redis_client.delete(webhook_key)
            return True
        except Exception as e:
            logger.error(f"Error removing webhook: {e}")
            return False


@celery_app.task(bind=True, max_retries=3)
def send_webhook_retry(self, webhook_config_dict: dict, event_dict: dict, retry_count: int):
    """Celery task for webhook retries"""
    import asyncio
    from app.database import AsyncSessionLocal
    
    async def _send_webhook():
        async with AsyncSessionLocal() as db:
            webhook_service = WebhookService(db)
            webhook_config = WebhookConfig(**webhook_config_dict)
            event = GeofenceEvent(**event_dict)
            
            success = await webhook_service.send_webhook(webhook_config, event, retry_count)
            return success
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(_send_webhook())
        
        if not success:
            self.retry(countdown=60)  # Retry after 1 minute
            
    except Exception as exc:
        logger.error(f"Webhook retry task failed: {exc}")
        self.retry(exc=exc, countdown=60)


class WebhookEventProcessor:
    """Process geofence events and trigger webhooks"""
    
    def __init__(self):
        self.processing = False
    
    async def start_processing(self):
        """Start processing geofence events for webhooks"""
        if self.processing:
            return
        
        self.processing = True
        
        # Subscribe to geofence events
        try:
            pubsub = redis_client.redis.pubsub()
            await pubsub.subscribe("geofence_events")
            
            async for message in pubsub.listen():
                if not self.processing:
                    break
                
                if message["type"] == "message":
                    try:
                        await self._process_event(json.loads(message["data"]))
                    except Exception as e:
                        logger.error(f"Error processing webhook event: {e}")
                        
        except Exception as e:
            logger.error(f"Error in webhook event processor: {e}")
        finally:
            self.processing = False
    
    async def _process_event(self, event_data: dict):
        """Process a single geofence event"""
        try:
            event = GeofenceEvent(
                device_id=uuid.UUID(event_data["device_id"]),
                geofence_id=uuid.UUID(event_data["geofence_id"]),
                event_type=event_data["event_type"],
                location=event_data["location"],
                timestamp=datetime.fromisoformat(event_data["timestamp"]),
                metadata=event_data.get("metadata", {})
            )
            
            # Get webhook configurations for this geofence
            async with AsyncSessionLocal() as db:
                webhook_service = WebhookService(db)
                
                # For now, we'll get from Redis. In a real implementation,
                # you'd get the user_id from the device information
                user_id = event_data.get("user_id")
                if user_id:
                    webhook_config = await webhook_service.get_webhooks_for_geofence(
                        uuid.UUID(user_id), event.geofence_id
                    )
                    
                    if webhook_config and webhook_config.is_active:
                        await webhook_service.send_webhook(webhook_config, event)
                    
        except Exception as e:
            logger.error(f"Error processing webhook event: {e}")
    
    def stop_processing(self):
        """Stop processing events"""
        self.processing = False


# Global webhook processor
webhook_processor = WebhookEventProcessor()


class WebhookDeliveryTracker:
    """Track webhook delivery statistics"""
    
    def __init__(self):
        pass
    
    async def record_delivery_attempt(
        self, 
        webhook_url: str, 
        event_type: str, 
        success: bool,
        response_time_ms: int = None,
        status_code: int = None
    ):
        """Record a webhook delivery attempt"""
        timestamp = datetime.utcnow()
        
        delivery_record = {
            "webhook_url": webhook_url,
            "event_type": event_type,
            "success": success,
            "timestamp": timestamp.isoformat(),
            "response_time_ms": response_time_ms,
            "status_code": status_code
        }
        
        # Store in Redis with expiry
        key = f"webhook_delivery:{timestamp.strftime('%Y%m%d')}:{webhook_url}"
        try:
            await redis_client.lpush(key, json.dumps(delivery_record))
            await redis_client.expire(key, 86400 * 7)  # Keep for 7 days
        except Exception as e:
            logger.error(f"Error recording webhook delivery: {e}")
    
    async def get_delivery_stats(
        self, 
        webhook_url: str, 
        days: int = 7
    ) -> Dict:
        """Get webhook delivery statistics"""
        total_attempts = 0
        successful_attempts = 0
        failed_attempts = 0
        avg_response_time = 0
        
        # Aggregate stats from Redis
        # This is a simplified implementation
        
        return {
            "webhook_url": webhook_url,
            "period_days": days,
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
            "failed_attempts": failed_attempts,
            "success_rate": successful_attempts / max(total_attempts, 1),
            "average_response_time_ms": avg_response_time
        }