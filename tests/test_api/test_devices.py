"""
Integration tests for device API endpoints.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestDeviceAPI:
    """Integration tests for device endpoints."""

    async def test_create_device_success(
        self, authenticated_client: AsyncClient, test_data_generator
    ):
        """Test successful device creation via API."""
        # Arrange
        device_data = test_data_generator.create_device_data(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            device_name="Integration Test Device"
        )
        
        # Act
        response = await authenticated_client.post(
            "/api/v1/devices",
            json=device_data
        )
        
        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["device_name"] == device_data["device_name"]
        assert data["device_type"] == device_data["device_type"]
        assert "id" in data
        assert data["is_active"] is True

    async def test_create_device_invalid_data(
        self, authenticated_client: AsyncClient
    ):
        """Test device creation with invalid data."""
        # Arrange
        invalid_data = {
            "device_name": "",  # Empty name
            "device_type": "invalid_type"
        }
        
        # Act
        response = await authenticated_client.post(
            "/api/v1/devices",
            json=invalid_data
        )
        
        # Assert
        assert response.status_code == 422

    async def test_get_device_success(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test successful device retrieval."""
        # Act
        response = await authenticated_client.get(
            f"/api/v1/devices/{sample_device.id}"
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_device.id
        assert data["device_name"] == sample_device.device_name

    async def test_get_device_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Test device retrieval with non-existent ID."""
        # Arrange
        non_existent_id = str(uuid4())
        
        # Act
        response = await authenticated_client.get(
            f"/api/v1/devices/{non_existent_id}"
        )
        
        # Assert
        assert response.status_code == 404

    async def test_get_devices_list(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test retrieving list of user's devices."""
        # Act
        response = await authenticated_client.get("/api/v1/devices")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(device["id"] == sample_device.id for device in data)

    async def test_update_device_location(
        self, authenticated_client: AsyncClient, sample_device, test_data_generator
    ):
        """Test updating device location."""
        # Arrange
        location_data = test_data_generator.create_location_data(
            lat=52.516275, lng=13.377704
        )
        
        # Act
        response = await authenticated_client.put(
            f"/api/v1/devices/{sample_device.id}/location",
            json=location_data
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["last_latitude"] == location_data["latitude"]
        assert data["last_longitude"] == location_data["longitude"]
        assert data["last_seen"] is not None

    async def test_update_device_location_invalid_coordinates(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test updating device location with invalid coordinates."""
        # Arrange
        invalid_location = {
            "latitude": 91.0,  # Invalid latitude
            "longitude": 13.404954,
            "timestamp": "2025-07-16T12:00:00Z"
        }
        
        # Act
        response = await authenticated_client.put(
            f"/api/v1/devices/{sample_device.id}/location",
            json=invalid_location
        )
        
        # Assert
        assert response.status_code == 422

    async def test_delete_device(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test device deletion."""
        # Act
        response = await authenticated_client.delete(
            f"/api/v1/devices/{sample_device.id}"
        )
        
        # Assert
        assert response.status_code == 204
        
        # Verify device is deleted
        get_response = await authenticated_client.get(
            f"/api/v1/devices/{sample_device.id}"
        )
        assert get_response.status_code == 404

    async def test_find_nearby_devices(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test finding devices within radius."""
        # Arrange
        query_params = {
            "latitude": 52.520008,
            "longitude": 13.404954,
            "radius_meters": 5000
        }
        
        # Act
        response = await authenticated_client.get(
            "/api/v1/devices/nearby",
            params=query_params
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_device_trajectory(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test retrieving device trajectory."""
        # Act
        response = await authenticated_client.get(
            f"/api/v1/devices/{sample_device.id}/trajectory"
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "trajectory_points" in data or data is None

    async def test_device_batch_location_update(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test batch location updates for multiple devices."""
        # Arrange
        batch_data = {
            "updates": [
                {
                    "device_id": sample_device.id,
                    "latitude": 52.520008,
                    "longitude": 13.404954,
                    "timestamp": "2025-07-16T12:00:00Z"
                }
            ]
        }
        
        # Act
        response = await authenticated_client.post(
            "/api/v1/devices/batch-location-update",
            json=batch_data
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "updated_devices" in data
        assert len(data["updated_devices"]) == 1

    async def test_unauthorized_access(self, test_client: AsyncClient):
        """Test accessing device endpoints without authentication."""
        # Act
        response = await test_client.get("/api/v1/devices")
        
        # Assert
        assert response.status_code == 401

    async def test_device_filtering(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test device filtering by various criteria."""
        # Test filtering by device type
        response = await authenticated_client.get(
            "/api/v1/devices",
            params={"device_type": "smartphone"}
        )
        
        assert response.status_code == 200
        data = response.json()
        for device in data:
            assert device["device_type"] == "smartphone"

    async def test_device_pagination(
        self, authenticated_client: AsyncClient
    ):
        """Test device list pagination."""
        # Act
        response = await authenticated_client.get(
            "/api/v1/devices",
            params={"skip": 0, "limit": 10}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    async def test_device_search(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test device search functionality."""
        # Act
        response = await authenticated_client.get(
            "/api/v1/devices/search",
            params={"query": sample_device.device_name[:4]}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_device_statistics(
        self, authenticated_client: AsyncClient
    ):
        """Test device statistics endpoint."""
        # Act
        response = await authenticated_client.get("/api/v1/devices/stats")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "total_devices" in data
        assert "active_devices" in data
        assert "device_types" in data

    async def test_device_export(
        self, authenticated_client: AsyncClient
    ):
        """Test device data export."""
        # Act
        response = await authenticated_client.get(
            "/api/v1/devices/export",
            params={"format": "csv"}
        )
        
        # Assert
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"

    async def test_device_geofence_events(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test retrieving geofence events for a device."""
        # Act
        response = await authenticated_client.get(
            f"/api/v1/devices/{sample_device.id}/geofence-events"
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_rate_limiting(
        self, authenticated_client: AsyncClient
    ):
        """Test rate limiting on device endpoints."""
        # This test would make multiple rapid requests to test rate limiting
        # In a real scenario, you'd configure lower rate limits for testing
        responses = []
        
        for _ in range(5):  # Make 5 rapid requests
            response = await authenticated_client.get("/api/v1/devices")
            responses.append(response.status_code)
        
        # All should succeed under normal rate limits
        assert all(status == 200 for status in responses)

    async def test_concurrent_device_updates(
        self, authenticated_client: AsyncClient, sample_device, test_data_generator
    ):
        """Test concurrent device location updates."""
        import asyncio
        
        # Arrange
        async def update_location(lat_offset: float):
            location_data = test_data_generator.create_location_data(
                lat=52.520008 + lat_offset,
                lng=13.404954
            )
            return await authenticated_client.put(
                f"/api/v1/devices/{sample_device.id}/location",
                json=location_data
            )
        
        # Act - Make concurrent updates
        tasks = [update_location(i * 0.001) for i in range(3)]
        responses = await asyncio.gather(*tasks)
        
        # Assert - All updates should succeed
        assert all(response.status_code == 200 for response in responses)

    async def test_device_metadata_operations(
        self, authenticated_client: AsyncClient, sample_device
    ):
        """Test device metadata operations."""
        # Test updating metadata
        metadata_update = {
            "metadata": {
                "manufacturer": "Apple",
                "model": "iPhone 13",
                "os_version": "iOS 15.0"
            }
        }
        
        response = await authenticated_client.patch(
            f"/api/v1/devices/{sample_device.id}",
            json=metadata_update
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["metadata"] == metadata_update["metadata"]