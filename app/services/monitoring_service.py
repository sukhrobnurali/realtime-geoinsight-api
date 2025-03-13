import asyncio
import json
from typing import Dict, List, Optional, Set
from datetime import datetime
import uuid

from app.services.redis_client import redis_client
from app.services.geofence_service import GeofenceService
from app.schemas.geofence import GeofenceEvent, Coordinates
from app.database import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)


class GeofenceMonitoringService:
    def __init__(self):
        self.active_devices: Dict[str, Dict] = {}
        self.device_geofence_states: Dict[str, Set[str]] = {}
        
    async def process_location_update(
        self, 
        device_id: str, 
        lat: float, 
        lon: float,
        user_id: str,
        metadata: Optional[Dict] = None
    ) -> List[GeofenceEvent]:
        """Process a location update and check for geofence events"""
        events = []
        
        try:
            async with AsyncSessionLocal() as db:
                geofence_service = GeofenceService(db)
                
                # Get current geofences containing the point
                current_geofences = await geofence_service.get_geofences_containing_point(
                    uuid.UUID(user_id), lat, lon
                )
                current_geofence_ids = {str(gf.id) for gf in current_geofences}
                
                # Get previous state
                previous_geofence_ids = self.device_geofence_states.get(device_id, set())
                
                # Calculate entered and exited geofences
                entered_geofences = current_geofence_ids - previous_geofence_ids
                exited_geofences = previous_geofence_ids - current_geofence_ids
                
                # Create enter events
                for geofence_id in entered_geofences:
                    event = GeofenceEvent(
                        device_id=uuid.UUID(device_id),
                        geofence_id=uuid.UUID(geofence_id),
                        event_type="enter",
                        location=Coordinates(lat=lat, lon=lon),
                        timestamp=datetime.utcnow(),
                        metadata=metadata or {}
                    )
                    events.append(event)
                    
                    # Publish to Redis
                    await self._publish_event(event)
                
                # Create exit events
                for geofence_id in exited_geofences:
                    event = GeofenceEvent(
                        device_id=uuid.UUID(device_id),
                        geofence_id=uuid.UUID(geofence_id),
                        event_type="exit",
                        location=Coordinates(lat=lat, lon=lon),
                        timestamp=datetime.utcnow(),
                        metadata=metadata or {}
                    )
                    events.append(event)
                    
                    # Publish to Redis
                    await self._publish_event(event)
                
                # Update device state
                self.device_geofence_states[device_id] = current_geofence_ids
                self.active_devices[device_id] = {
                    "last_location": {"lat": lat, "lon": lon},
                    "last_update": datetime.utcnow().isoformat(),
                    "user_id": user_id,
                    "current_geofences": list(current_geofence_ids)
                }
                
                # Store in Redis for persistence
                await self._store_device_state(device_id)
                
        except Exception as e:
            logger.error(f"Error processing location update for device {device_id}: {e}")
        
        return events
    
    async def _publish_event(self, event: GeofenceEvent):
        """Publish geofence event to Redis pub/sub"""
        try:
            event_data = {
                "device_id": str(event.device_id),
                "geofence_id": str(event.geofence_id),
                "event_type": event.event_type,
                "location": {"lat": event.location.lat, "lon": event.location.lon},
                "timestamp": event.timestamp.isoformat(),
                "metadata": event.metadata
            }
            
            # Publish to general geofence events channel
            await redis_client.publish("geofence_events", event_data)
            
            # Publish to device-specific channel
            await redis_client.publish(f"device:{event.device_id}:events", event_data)
            
            # Publish to geofence-specific channel
            await redis_client.publish(f"geofence:{event.geofence_id}:events", event_data)
            
        except Exception as e:
            logger.error(f"Error publishing event: {e}")
    
    async def _store_device_state(self, device_id: str):
        """Store device state in Redis"""
        try:
            if device_id in self.active_devices:
                device_data = self.active_devices[device_id].copy()
                device_data["geofence_states"] = list(self.device_geofence_states.get(device_id, set()))
                
                await redis_client.set(
                    f"device_state:{device_id}",
                    json.dumps(device_data),
                    expire=86400  # 24 hours
                )
        except Exception as e:
            logger.error(f"Error storing device state: {e}")
    
    async def _load_device_state(self, device_id: str):
        """Load device state from Redis"""
        try:
            state_data = await redis_client.get(f"device_state:{device_id}")
            if state_data:
                data = json.loads(state_data)
                self.active_devices[device_id] = {
                    "last_location": data.get("last_location"),
                    "last_update": data.get("last_update"),
                    "user_id": data.get("user_id"),
                    "current_geofences": data.get("current_geofences", [])
                }
                self.device_geofence_states[device_id] = set(data.get("geofence_states", []))
        except Exception as e:
            logger.error(f"Error loading device state: {e}")
    
    async def get_device_status(self, device_id: str) -> Optional[Dict]:
        """Get current status of a device"""
        # Try to load from memory first, then Redis
        if device_id not in self.active_devices:
            await self._load_device_state(device_id)
        
        return self.active_devices.get(device_id)
    
    async def get_active_devices(self) -> Dict[str, Dict]:
        """Get all active devices"""
        return self.active_devices.copy()
    
    async def remove_device(self, device_id: str):
        """Remove device from monitoring"""
        self.active_devices.pop(device_id, None)
        self.device_geofence_states.pop(device_id, None)
        
        # Remove from Redis
        try:
            await redis_client.delete(f"device_state:{device_id}")
        except Exception as e:
            logger.error(f"Error removing device state: {e}")
    
    async def subscribe_to_events(self, channel: str = "geofence_events"):
        """Subscribe to geofence events"""
        try:
            pubsub = redis_client.redis.pubsub()
            await pubsub.subscribe(channel)
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        event_data = json.loads(message["data"])
                        yield event_data
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON in message: {message['data']}")
                        
        except Exception as e:
            logger.error(f"Error subscribing to events: {e}")


# Global monitoring service instance
monitoring_service = GeofenceMonitoringService()


class RealtimeLocationProcessor:
    """Process real-time location updates in batches"""
    
    def __init__(self, batch_size: int = 100, flush_interval: float = 1.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.location_queue = asyncio.Queue()
        self.processing = False
    
    async def add_location_update(
        self, 
        device_id: str, 
        lat: float, 
        lon: float,
        user_id: str,
        metadata: Optional[Dict] = None
    ):
        """Add a location update to the processing queue"""
        await self.location_queue.put({
            "device_id": device_id,
            "lat": lat,
            "lon": lon,
            "user_id": user_id,
            "metadata": metadata,
            "timestamp": datetime.utcnow()
        })
    
    async def start_processing(self):
        """Start processing location updates"""
        if self.processing:
            return
        
        self.processing = True
        
        while self.processing:
            batch = []
            
            try:
                # Collect a batch of location updates
                while len(batch) < self.batch_size:
                    try:
                        update = await asyncio.wait_for(
                            self.location_queue.get(),
                            timeout=self.flush_interval
                        )
                        batch.append(update)
                    except asyncio.TimeoutError:
                        break
                
                # Process the batch
                if batch:
                    await self._process_batch(batch)
                    
            except Exception as e:
                logger.error(f"Error in location processing: {e}")
                await asyncio.sleep(1)
    
    async def _process_batch(self, batch: List[Dict]):
        """Process a batch of location updates"""
        tasks = []
        
        for update in batch:
            task = monitoring_service.process_location_update(
                update["device_id"],
                update["lat"],
                update["lon"],
                update["user_id"],
                update["metadata"]
            )
            tasks.append(task)
        
        # Process all updates concurrently
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log any errors
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing update {i}: {result}")
                    
        except Exception as e:
            logger.error(f"Error processing batch: {e}")
    
    def stop_processing(self):
        """Stop processing location updates"""
        self.processing = False


# Global location processor
location_processor = RealtimeLocationProcessor()