"""
Unit tests for the device service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from uuid import uuid4

from app.services.device_service import DeviceService
from app.models.device import Device
from app.schemas.device import DeviceCreate, LocationUpdate
from app.utils.monitoring import ErrorSeverity


class TestDeviceService:
    """Test cases for DeviceService."""

    @pytest.fixture
    def device_service(self, mock_redis):
        """Create device service instance with mocked dependencies."""
        service = DeviceService()
        service.redis = mock_redis
        return service

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def sample_device_create(self):
        """Sample device creation data."""
        return DeviceCreate(
            device_name="Test Device",
            device_type="smartphone",
            metadata={"manufacturer": "Apple", "model": "iPhone 12"}
        )

    @pytest.fixture
    def sample_location_update(self):
        """Sample location update data."""
        return LocationUpdate(
            latitude=52.520008,
            longitude=13.404954,
            timestamp=datetime.utcnow(),
            accuracy=5.0,
            speed=15.5,
            heading=180.0
        )

    async def test_create_device_success(
        self, device_service, mock_db_session, sample_device_create, mock_current_user
    ):
        """Test successful device creation."""
        # Arrange
        user_id = mock_current_user.id
        
        # Mock successful database operations
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        
        # Act
        result = await device_service.create_device(
            mock_db_session, user_id, sample_device_create
        )
        
        # Assert
        assert result is not None
        assert result.device_name == sample_device_create.device_name
        assert result.device_type == sample_device_create.device_type
        assert result.user_id == user_id
        assert result.is_active is True
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    async def test_create_device_duplicate_name(
        self, device_service, mock_db_session, sample_device_create, mock_current_user
    ):
        """Test device creation with duplicate name."""
        # Arrange
        user_id = mock_current_user.id
        existing_device = Device(
            id=str(uuid4()),
            user_id=user_id,
            device_name=sample_device_create.device_name,
            device_type="existing"
        )
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = existing_device
        
        # Act & Assert
        with pytest.raises(ValueError, match="Device with this name already exists"):
            await device_service.create_device(
                mock_db_session, user_id, sample_device_create
            )

    async def test_get_device_success(
        self, device_service, mock_db_session, mock_current_user
    ):
        """Test successful device retrieval."""
        # Arrange
        device_id = str(uuid4())
        user_id = mock_current_user.id
        expected_device = Device(
            id=device_id,
            user_id=user_id,
            device_name="Test Device",
            device_type="smartphone"
        )
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = expected_device
        
        # Act
        result = await device_service.get_device(mock_db_session, device_id, user_id)
        
        # Assert
        assert result == expected_device

    async def test_get_device_not_found(
        self, device_service, mock_db_session, mock_current_user
    ):
        """Test device retrieval when device doesn't exist."""
        # Arrange
        device_id = str(uuid4())
        user_id = mock_current_user.id
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        
        # Act
        result = await device_service.get_device(mock_db_session, device_id, user_id)
        
        # Assert
        assert result is None

    async def test_update_device_location_success(
        self, device_service, mock_db_session, sample_location_update, mock_current_user
    ):
        """Test successful device location update."""
        # Arrange
        device_id = str(uuid4())
        user_id = mock_current_user.id
        existing_device = Device(
            id=device_id,
            user_id=user_id,
            device_name="Test Device",
            device_type="smartphone"
        )
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = existing_device
        
        # Act
        result = await device_service.update_device_location(
            mock_db_session, device_id, user_id, sample_location_update
        )
        
        # Assert
        assert result is not None
        assert result.last_latitude == sample_location_update.latitude
        assert result.last_longitude == sample_location_update.longitude
        assert result.last_seen is not None
        mock_db_session.commit.assert_called_once()

    async def test_update_device_location_not_found(
        self, device_service, mock_db_session, sample_location_update, mock_current_user
    ):
        """Test location update when device doesn't exist."""
        # Arrange
        device_id = str(uuid4())
        user_id = mock_current_user.id
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        
        # Act
        result = await device_service.update_device_location(
            mock_db_session, device_id, user_id, sample_location_update
        )
        
        # Assert
        assert result is None

    async def test_get_devices_for_user(
        self, device_service, mock_db_session, mock_current_user
    ):
        """Test retrieving all devices for a user."""
        # Arrange
        user_id = mock_current_user.id
        expected_devices = [
            Device(id=str(uuid4()), user_id=user_id, device_name="Device 1", device_type="smartphone"),
            Device(id=str(uuid4()), user_id=user_id, device_name="Device 2", device_type="tablet")
        ]
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = expected_devices
        mock_db_session.execute.return_value = mock_result
        
        # Act
        result = await device_service.get_devices_for_user(mock_db_session, user_id)
        
        # Assert
        assert len(result) == 2
        assert result == expected_devices

    async def test_delete_device_success(
        self, device_service, mock_db_session, mock_current_user
    ):
        """Test successful device deletion."""
        # Arrange
        device_id = str(uuid4())
        user_id = mock_current_user.id
        existing_device = Device(
            id=device_id,
            user_id=user_id,
            device_name="Test Device",
            device_type="smartphone"
        )
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = existing_device
        
        # Act
        result = await device_service.delete_device(mock_db_session, device_id, user_id)
        
        # Assert
        assert result is True
        mock_db_session.delete.assert_called_once_with(existing_device)
        mock_db_session.commit.assert_called_once()

    async def test_delete_device_not_found(
        self, device_service, mock_db_session, mock_current_user
    ):
        """Test device deletion when device doesn't exist."""
        # Arrange
        device_id = str(uuid4())
        user_id = mock_current_user.id
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        
        # Act
        result = await device_service.delete_device(mock_db_session, device_id, user_id)
        
        # Assert
        assert result is False

    async def test_find_devices_within_radius(
        self, device_service, mock_db_session, mock_current_user
    ):
        """Test finding devices within a specific radius."""
        # Arrange
        user_id = mock_current_user.id
        center_lat = 52.520008
        center_lng = 13.404954
        radius_m = 1000
        
        expected_devices = [
            Device(
                id=str(uuid4()),
                user_id=user_id,
                device_name="Nearby Device 1",
                device_type="smartphone",
                last_latitude=52.521000,
                last_longitude=13.405000
            )
        ]
        
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = expected_devices
        mock_db_session.execute.return_value = mock_result
        
        # Act
        result = await device_service.find_devices_within_radius(
            mock_db_session, user_id, center_lat, center_lng, radius_m
        )
        
        # Assert
        assert len(result) == 1
        assert result[0].device_name == "Nearby Device 1"

    async def test_get_device_trajectory(
        self, device_service, mock_db_session, mock_current_user
    ):
        """Test retrieving device trajectory data."""
        # Arrange
        device_id = str(uuid4())
        user_id = mock_current_user.id
        hours = 24
        
        # Mock trajectory data
        from app.models.trajectory import Trajectory, TrajectoryPoint
        
        trajectory = Trajectory(
            id=str(uuid4()),
            device_id=device_id,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow()
        )
        
        trajectory_points = [
            TrajectoryPoint(
                trajectory_id=trajectory.id,
                latitude=52.520008,
                longitude=13.404954,
                timestamp=datetime.utcnow()
            )
        ]
        
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = trajectory
        mock_db_session.execute.return_value = mock_result
        
        # Act
        result = await device_service.get_device_trajectory(
            mock_db_session, device_id, user_id, hours
        )
        
        # Assert
        assert result is not None

    async def test_redis_caching(self, device_service, mock_redis, mock_db_session):
        """Test Redis caching functionality."""
        # Arrange
        cache_key = "test_key"
        cache_value = {"test": "data"}
        
        # Test cache miss and set
        mock_redis.get.return_value = None
        await device_service._cache_set(cache_key, cache_value, 3600)
        
        # Assert
        mock_redis.setex.assert_called_once()
        
        # Test cache hit
        import json
        mock_redis.get.return_value = json.dumps(cache_value)
        result = await device_service._cache_get(cache_key)
        
        # Assert
        assert result == cache_value

    async def test_error_handling(
        self, device_service, mock_db_session, sample_device_create, mock_current_user
    ):
        """Test error handling in device operations."""
        # Arrange
        user_id = mock_current_user.id
        mock_db_session.commit.side_effect = Exception("Database error")
        
        # Act & Assert
        with pytest.raises(Exception):
            await device_service.create_device(
                mock_db_session, user_id, sample_device_create
            )
        
        # Verify rollback was called
        mock_db_session.rollback.assert_called_once()

    async def test_location_validation(self, device_service):
        """Test location data validation."""
        # Test valid coordinates
        assert device_service._validate_coordinates(52.520008, 13.404954) is True
        
        # Test invalid latitude
        assert device_service._validate_coordinates(91.0, 13.404954) is False
        assert device_service._validate_coordinates(-91.0, 13.404954) is False
        
        # Test invalid longitude
        assert device_service._validate_coordinates(52.520008, 181.0) is False
        assert device_service._validate_coordinates(52.520008, -181.0) is False

    async def test_distance_calculation(self, device_service):
        """Test distance calculation between two points."""
        # Berlin center to Brandenburg Gate (approximately 2.5km)
        lat1, lng1 = 52.520008, 13.404954
        lat2, lng2 = 52.516275, 13.377704
        
        distance = device_service._calculate_distance(lat1, lng1, lat2, lng2)
        
        # Assert distance is approximately correct (within 100m tolerance)
        assert 2400 <= distance <= 2600

    async def test_performance_metrics(self, device_service, mock_db_session):
        """Test performance monitoring integration."""
        # This would test that performance metrics are collected
        # during device operations
        pass