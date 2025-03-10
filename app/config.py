from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://geoapi:password@localhost:5432/geoapi_db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Security
    secret_key: str = "your-secret-key-here"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # External APIs
    mapbox_api_key: Optional[str] = None
    openstreetmap_api_key: Optional[str] = None
    
    # Environment
    environment: str = "development"
    debug: bool = True
    
    # CORS
    backend_cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]
    
    # Rate Limiting
    rate_limit_per_minute: int = 60
    
    # App Info
    app_name: str = "GeoInsight API"
    app_version: str = "1.0.0"
    
    class Config:
        env_file = ".env"


settings = Settings()