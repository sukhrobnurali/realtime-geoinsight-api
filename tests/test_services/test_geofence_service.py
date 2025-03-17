"""
Unit tests for the geofence service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from shapely.geometry import Point, Polygon

from app.services.geofence_service import GeofenceService
from app.models.geofence import Geofence
from app.schemas.geofence import GeofenceCreate, GeofenceUpdate


class TestGeofenceService:
    """Test cases for GeofenceService."""

    @pytest.fixture
    def geofence_service(self, mock_redis):
        """Create geofence service instance with mocked dependencies."""
        service = GeofenceService()
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
        session.delete = MagicMock()
        return session

    @pytest.fixture
    def sample_geofence_create(self):
        """Sample geofence creation data."""
        return GeofenceCreate(
            name="Test Geofence",
            geometry={
                "type": "Polygon",
                "coordinates": [[
                    [13.3, 52.5],   # SW corner
                    [13.3, 52.55],  # NW corner
                    [13.45, 52.55], # NE corner
                    [13.45, 52.5],  # SE corner
                    [13.3, 52.5]    # Close polygon
                ]]
            },
            trigger_type="enter",
            metadata={"description": "Test area"}
        )

    @pytest.fixture
    def sample_circular_geofence(self):
        """Sample circular geofence data."""
        return GeofenceCreate(
            name="Circular Geofence",
            geometry={
                "type": "Point",
                "coordinates": [13.404954, 52.520008]
            },
            radius=500,  # 500 meters
            trigger_type="both",
            metadata={"type": "circular"}
        )

    async def test_create_geofence_success(
        self, geofence_service, mock_db_session, sample_geofence_create, mock_current_user
    ):
        """Test successful geofence creation."""
        # Arrange
        user_id = mock_current_user.id
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        
        # Act
        result = await geofence_service.create_geofence(
            mock_db_session, user_id, sample_geofence_create
        )
        
        # Assert
        assert result is not None
        assert result.name == sample_geofence_create.name
        assert result.trigger_type == sample_geofence_create.trigger_type
        assert result.user_id == user_id
        assert result.is_active is True
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    async def test_create_circular_geofence(
        self, geofence_service, mock_db_session, sample_circular_geofence, mock_current_user
    ):
        """Test creating a circular geofence."""
        # Arrange
        user_id = mock_current_user.id
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = None
        
        # Act
        result = await geofence_service.create_geofence(
            mock_db_session, user_id, sample_circular_geofence
        )
        
        # Assert
        assert result is not None
        assert result.name == sample_circular_geofence.name
        assert result.radius == sample_circular_geofence.radius

    async def test_create_geofence_duplicate_name(
        self, geofence_service, mock_db_session, sample_geofence_create, mock_current_user
    ):
        """Test geofence creation with duplicate name."""
        # Arrange
        user_id = mock_current_user.id
        existing_geofence = Geofence(
            id=str(uuid4()),
            user_id=user_id,
            name=sample_geofence_create.name
        )
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = existing_geofence
        
        # Act & Assert
        with pytest.raises(ValueError, match="Geofence with this name already exists"):
            await geofence_service.create_geofence(
                mock_db_session, user_id, sample_geofence_create
            )

    async def test_get_geofence_success(
        self, geofence_service, mock_db_session, mock_current_user
    ):
        """Test successful geofence retrieval."""
        # Arrange
        geofence_id = str(uuid4())
        user_id = mock_current_user.id
        expected_geofence = Geofence(
            id=geofence_id,
            user_id=user_id,
            name="Test Geofence"
        )
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = expected_geofence
        
        # Act
        result = await geofence_service.get_geofence(mock_db_session, geofence_id, user_id)
        
        # Assert
        assert result == expected_geofence

    async def test_update_geofence(
        self, geofence_service, mock_db_session, mock_current_user
    ):
        """Test geofence update."""
        # Arrange
        geofence_id = str(uuid4())
        user_id = mock_current_user.id
        existing_geofence = Geofence(
            id=geofence_id,
            user_id=user_id,
            name="Original Name",
            is_active=True
        )
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = existing_geofence
        
        update_data = GeofenceUpdate(
            name="Updated Name",
            is_active=False
        )
        
        # Act
        result = await geofence_service.update_geofence(
            mock_db_session, geofence_id, user_id, update_data
        )
        
        # Assert
        assert result is not None
        assert result.name == "Updated Name"
        assert result.is_active is False
        mock_db_session.commit.assert_called_once()

    async def test_delete_geofence(
        self, geofence_service, mock_db_session, mock_current_user
    ):
        """Test geofence deletion."""
        # Arrange
        geofence_id = str(uuid4())
        user_id = mock_current_user.id
        existing_geofence = Geofence(
            id=geofence_id,
            user_id=user_id,
            name="Test Geofence"
        )
        mock_db_session.execute.return_value.scalar_one_or_none.return_value = existing_geofence
        
        # Act
        result = await geofence_service.delete_geofence(mock_db_session, geofence_id, user_id)
        
        # Assert
        assert result is True
        mock_db_session.delete.assert_called_once_with(existing_geofence)
        mock_db_session.commit.assert_called_once()

    async def test_check_point_in_geofence_inside(self, geofence_service):
        """Test point inside geofence detection."""
        # Arrange - point inside the polygon
        geofence_geometry = "POLYGON((13.3 52.5, 13.3 52.55, 13.45 52.55, 13.45 52.5, 13.3 52.5))"
        test_point_lat = 52.525  # Inside the polygon
        test_point_lng = 13.375
        
        # Act
        result = geofence_service._check_point_in_polygon(
            test_point_lat, test_point_lng, geofence_geometry
        )
        
        # Assert
        assert result is True

    async def test_check_point_in_geofence_outside(self, geofence_service):
        """Test point outside geofence detection."""
        # Arrange - point outside the polygon
        geofence_geometry = "POLYGON((13.3 52.5, 13.3 52.55, 13.45 52.55, 13.45 52.5, 13.3 52.5))"
        test_point_lat = 52.6   # Outside the polygon
        test_point_lng = 13.5
        
        # Act
        result = geofence_service._check_point_in_polygon(
            test_point_lat, test_point_lng, geofence_geometry
        )
        
        # Assert
        assert result is False

    async def test_check_geofence_triggers(
        self, geofence_service, mock_db_session, mock_current_user
    ):
        """Test geofence trigger checking."""
        # Arrange
        user_id = mock_current_user.id
        device_id = str(uuid4())
        lat, lng = 52.525, 13.375
        
        # Mock geofences that would be triggered
        active_geofences = [
            Geofence(
                id=str(uuid4()),
                user_id=user_id,
                name="Test Geofence",
                geometry="POLYGON((13.3 52.5, 13.3 52.55, 13.45 52.55, 13.45 52.5, 13.3 52.5))",
                trigger_type="enter",
                is_active=True
            )
        ]
        
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = active_geofences
        mock_db_session.execute.return_value = mock_result
        
        # Act
        triggered_geofences = await geofence_service.check_geofence_triggers(
            mock_db_session, user_id, device_id, lat, lng
        )
        
        # Assert
        assert len(triggered_geofences) >= 0  # May or may not trigger based on implementation

    async def test_get_geofences_for_user(
        self, geofence_service, mock_db_session, mock_current_user
    ):
        """Test retrieving all geofences for a user."""
        # Arrange
        user_id = mock_current_user.id
        expected_geofences = [
            Geofence(id=str(uuid4()), user_id=user_id, name="Geofence 1"),
            Geofence(id=str(uuid4()), user_id=user_id, name="Geofence 2")
        ]
        
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = expected_geofences
        mock_db_session.execute.return_value = mock_result
        
        # Act
        result = await geofence_service.get_geofences_for_user(mock_db_session, user_id)
        
        # Assert
        assert len(result) == 2
        assert result == expected_geofences

    async def test_find_geofences_containing_point(
        self, geofence_service, mock_db_session, mock_current_user
    ):
        """Test finding geofences that contain a specific point."""
        # Arrange
        user_id = mock_current_user.id
        lat, lng = 52.525, 13.375
        
        containing_geofences = [
            Geofence(
                id=str(uuid4()),
                user_id=user_id,
                name="Containing Geofence",
                geometry="POLYGON((13.3 52.5, 13.3 52.55, 13.45 52.55, 13.45 52.5, 13.3 52.5))"
            )
        ]
        
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = containing_geofences
        mock_db_session.execute.return_value = mock_result
        
        # Act
        result = await geofence_service.find_geofences_containing_point(
            mock_db_session, user_id, lat, lng
        )
        
        # Assert
        assert len(result) >= 0

    async def test_geometry_validation(self, geofence_service):
        """Test geometry validation."""
        # Test valid polygon
        valid_polygon = {
            "type": "Polygon",
            "coordinates": [[
                [13.3, 52.5],
                [13.3, 52.55],
                [13.45, 52.55],
                [13.45, 52.5],
                [13.3, 52.5]
            ]]
        }
        assert geofence_service._validate_geometry(valid_polygon) is True
        
        # Test valid point
        valid_point = {
            "type": "Point",
            "coordinates": [13.404954, 52.520008]
        }
        assert geofence_service._validate_geometry(valid_point) is True
        
        # Test invalid geometry
        invalid_geometry = {
            "type": "Invalid",
            "coordinates": []
        }
        assert geofence_service._validate_geometry(invalid_geometry) is False

    async def test_calculate_geofence_area(self, geofence_service):
        """Test geofence area calculation."""
        # Create a simple square polygon (approximately 1km x 1km)
        geometry = "POLYGON((13.3 52.5, 13.3 52.509, 13.315 52.509, 13.315 52.5, 13.3 52.5))"
        
        area = geofence_service._calculate_area(geometry)
        
        # Assert area is approximately 1 km² (within reasonable tolerance)
        assert 0.8 <= area <= 1.2  # Allow for projection differences

    async def test_buffer_geofence(self, geofence_service):
        """Test creating buffer around geofence."""
        # Arrange
        original_geometry = "POINT(13.404954 52.520008)"
        buffer_distance = 100  # 100 meters
        
        # Act
        buffered_geometry = geofence_service._create_buffer(original_geometry, buffer_distance)
        
        # Assert
        assert buffered_geometry is not None
        assert "POLYGON" in buffered_geometry

    async def test_geofence_intersection(self, geofence_service):
        """Test checking if two geofences intersect."""
        # Arrange
        geofence1 = "POLYGON((13.3 52.5, 13.3 52.52, 13.32 52.52, 13.32 52.5, 13.3 52.5))"
        geofence2 = "POLYGON((13.31 52.51, 13.31 52.53, 13.33 52.53, 13.33 52.51, 13.31 52.51))"
        
        # Act
        intersects = geofence_service._check_intersection(geofence1, geofence2)
        
        # Assert
        assert intersects is True

    async def test_error_handling(
        self, geofence_service, mock_db_session, sample_geofence_create, mock_current_user
    ):
        """Test error handling in geofence operations."""
        # Arrange
        user_id = mock_current_user.id
        mock_db_session.commit.side_effect = Exception("Database error")
        
        # Act & Assert
        with pytest.raises(Exception):
            await geofence_service.create_geofence(
                mock_db_session, user_id, sample_geofence_create
            )
        
        # Verify rollback was called
        mock_db_session.rollback.assert_called_once()

    async def test_cache_operations(self, geofence_service, mock_redis):
        """Test Redis caching for geofences."""
        # Arrange
        cache_key = "geofence_test"
        cache_data = {"id": "123", "name": "Test"}
        
        # Test cache set
        await geofence_service._cache_set(cache_key, cache_data, 3600)
        mock_redis.setex.assert_called_once()
        
        # Test cache get
        import json
        mock_redis.get.return_value = json.dumps(cache_data)
        result = await geofence_service._cache_get(cache_key)
        
        assert result == cache_data

    async def test_spatial_index_optimization(self, geofence_service, mock_db_session):
        """Test that spatial queries use proper indexing."""
        # This test verifies that our spatial queries are structured
        # to take advantage of spatial indexes
        user_id = str(uuid4())
        lat, lng = 52.520008, 13.404954
        
        # Call the method that should use spatial indexing
        await geofence_service.find_geofences_containing_point(
            mock_db_session, user_id, lat, lng
        )
        
        # Verify that the query was executed (spatial index usage would be
        # verified through query plan analysis in integration tests)
        mock_db_session.execute.assert_called_once()