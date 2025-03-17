"""
Test configuration and shared fixtures for the geospatial API test suite.
"""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from httpx import AsyncClient
import redis
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.database import get_db, Base
from app.models.user import User
from app.models.device import Device
from app.models.geofence import Geofence
from app.services.redis_client import redis_client
from app.utils.auth import get_current_user


# Test database URL (in-memory SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture
async def test_client(test_session):
    """Create test client with dependency overrides."""
    
    # Override database dependency
    app.dependency_overrides[get_db] = lambda: test_session
    
    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.setex.return_value = True
    mock_redis.delete.return_value = True
    mock_redis.keys.return_value = []
    mock_redis.ping.return_value = "PONG"
    
    # Override Redis dependency
    redis_client.redis = mock_redis
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def mock_current_user():
    """Mock current user for authenticated endpoints."""
    user = User(
        id="550e8400-e29b-41d4-a716-446655440000",
        email="test@example.com",
        username="testuser",
        is_active=True,
        is_verified=True
    )
    return user


@pytest.fixture
def authenticated_client(test_client, mock_current_user):
    """Create authenticated test client."""
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_device(test_session, mock_current_user):
    """Create a sample device for testing."""
    device = Device(
        id="550e8400-e29b-41d4-a716-446655440001",
        user_id=mock_current_user.id,
        device_name="Test Device",
        device_type="smartphone",
        is_active=True
    )
    
    test_session.add(device)
    await test_session.commit()
    await test_session.refresh(device)
    
    return device


@pytest.fixture
async def sample_geofence(test_session, mock_current_user):
    """Create a sample geofence for testing."""
    geofence = Geofence(
        id="550e8400-e29b-41d4-a716-446655440002",
        user_id=mock_current_user.id,
        name="Test Geofence",
        geometry="POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",
        is_active=True
    )
    
    test_session.add(geofence)
    await test_session.commit()
    await test_session.refresh(geofence)
    
    return geofence


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    mock = AsyncMock()
    mock.get.return_value = None
    mock.set.return_value = True
    mock.setex.return_value = True
    mock.delete.return_value = True
    mock.keys.return_value = []
    mock.ping.return_value = "PONG"
    mock.pipeline.return_value = AsyncMock()
    mock.pipeline.return_value.execute.return_value = [True] * 10
    return mock


@pytest.fixture
def mock_osrm_response():
    """Mock OSRM API response for route testing."""
    return {
        "code": "Ok",
        "routes": [
            {
                "geometry": "mock_geometry_string",
                "legs": [
                    {
                        "steps": [],
                        "distance": 1000.0,
                        "duration": 120.0,
                        "summary": "",
                        "weight": 120.0
                    }
                ],
                "distance": 1000.0,
                "duration": 120.0,
                "weight_name": "routability",
                "weight": 120.0
            }
        ],
        "waypoints": [
            {
                "hint": "mock_hint_1",
                "distance": 0.0,
                "name": "",
                "location": [13.388860, 52.517037]
            },
            {
                "hint": "mock_hint_2", 
                "distance": 0.0,
                "name": "",
                "location": [13.397634, 52.529407]
            }
        ]
    }


@pytest.fixture
def spatial_test_data():
    """Provide test data for spatial operations."""
    return {
        "points": [
            {"lat": 52.520008, "lng": 13.404954},  # Berlin center
            {"lat": 52.516275, "lng": 13.377704},  # Brandenburg Gate
            {"lat": 52.500342, "lng": 13.425293},  # Alexanderplatz
        ],
        "polygon": [
            [13.3, 52.5],  # SW corner
            [13.3, 52.55], # NW corner
            [13.45, 52.55], # NE corner
            [13.45, 52.5],  # SE corner
            [13.3, 52.5]    # Close polygon
        ],
        "line": [
            [13.404954, 52.520008],
            [13.377704, 52.516275],
            [13.425293, 52.500342]
        ]
    }


@pytest.fixture
def performance_test_config():
    """Configuration for performance testing."""
    return {
        "concurrent_users": 10,
        "test_duration": 30,  # seconds
        "ramp_up_time": 5,    # seconds
        "endpoints_to_test": [
            "/api/v1/devices",
            "/api/v1/geofences", 
            "/api/v1/routes/optimize",
            "/api/v1/recommendations/nearby"
        ]
    }


# Test data generators
class TestDataGenerator:
    """Generate test data for various scenarios."""
    
    @staticmethod
    def create_device_data(user_id: str, device_name: str = "Test Device"):
        return {
            "device_name": device_name,
            "device_type": "smartphone",
            "metadata": {"test": True}
        }
    
    @staticmethod
    def create_location_data(lat: float = 52.520008, lng: float = 13.404954):
        return {
            "latitude": lat,
            "longitude": lng,
            "timestamp": "2025-07-16T12:00:00Z",
            "accuracy": 5.0,
            "speed": 0.0,
            "heading": 0.0
        }
    
    @staticmethod
    def create_geofence_data(name: str = "Test Geofence"):
        return {
            "name": name,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [13.3, 52.5],
                    [13.3, 52.55],
                    [13.45, 52.55],
                    [13.45, 52.5],
                    [13.3, 52.5]
                ]]
            },
            "trigger_type": "enter",
            "metadata": {"test": True}
        }
    
    @staticmethod
    def create_route_optimization_data():
        return {
            "start_location": {"latitude": 52.520008, "longitude": 13.404954},
            "end_location": {"latitude": 52.500342, "longitude": 13.425293},
            "waypoints": [
                {"latitude": 52.516275, "longitude": 13.377704}
            ],
            "optimization_type": "shortest_time",
            "constraints": {
                "max_distance_km": 50,
                "vehicle_type": "car"
            }
        }


@pytest.fixture
def test_data_generator():
    """Provide test data generator."""
    return TestDataGenerator


# Async test helper
def async_test(func):
    """Decorator for async test functions."""
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapper