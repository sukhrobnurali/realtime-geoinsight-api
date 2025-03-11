import redis.asyncio as redis
from typing import Optional
import json
from app.config import settings


class RedisClient:
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
    
    async def connect(self):
        self.redis = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20
        )
    
    async def disconnect(self):
        if self.redis:
            await self.redis.close()
    
    async def get(self, key: str) -> Optional[str]:
        if not self.redis:
            await self.connect()
        return await self.redis.get(key)
    
    async def set(self, key: str, value: str, expire: Optional[int] = None):
        if not self.redis:
            await self.connect()
        await self.redis.set(key, value, ex=expire)
    
    async def delete(self, key: str):
        if not self.redis:
            await self.connect()
        await self.redis.delete(key)
    
    async def exists(self, key: str) -> bool:
        if not self.redis:
            await self.connect()
        return bool(await self.redis.exists(key))
    
    async def publish(self, channel: str, message: dict):
        if not self.redis:
            await self.connect()
        await self.redis.publish(channel, json.dumps(message))
    
    async def lpush(self, key: str, *values):
        if not self.redis:
            await self.connect()
        await self.redis.lpush(key, *values)
    
    async def rpop(self, key: str) -> Optional[str]:
        if not self.redis:
            await self.connect()
        return await self.redis.rpop(key)


redis_client = RedisClient()