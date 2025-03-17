"""
Load testing configuration for the geospatial API using Locust.
"""

import random
import json
from locust import HttpUser, task, between
from uuid import uuid4


class GeospatialAPIUser(HttpUser):
    """Simulated user for load testing the geospatial API."""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    
    def on_start(self):
        """Set up user session."""
        self.api_key = "test-api-key"
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Create test data for the user
        self.user_id = str(uuid4())
        self.device_ids = []
        self.geofence_ids = []
        
        # Authenticate (simplified for testing)
        self.login()
        
        # Create some test devices and geofences
        self.setup_test_data()
    
    def login(self):
        """Simulate user authentication."""
        auth_data = {
            "username": f"testuser_{random.randint(1000, 9999)}",
            "password": "testpassword123"
        }
        
        # In a real scenario, this would authenticate and get a token
        response = self.client.post(
            "/api/v1/auth/login",
            json=auth_data,
            headers={"Content-Type": "application/json"},
            catch_response=True
        )
        
        if response.status_code == 200:
            # Extract token (simplified)
            self.headers["Authorization"] = "Bearer test-token"
            response.success()
        else:
            response.failure(f"Failed to authenticate: {response.status_code}")
    
    def setup_test_data(self):
        """Create test devices and geofences for load testing."""
        # Create 2-5 test devices per user
        num_devices = random.randint(2, 5)
        
        for i in range(num_devices):
            device_data = {
                "device_name": f"Load Test Device {i}",
                "device_type": random.choice(["smartphone", "tablet", "tracker"]),
                "metadata": {
                    "test": True,
                    "load_test_id": self.user_id
                }
            }
            
            response = self.client.post(
                "/api/v1/devices",
                json=device_data,
                headers=self.headers,
                catch_response=True
            )
            
            if response.status_code == 201:
                device_id = response.json().get("id")
                if device_id:
                    self.device_ids.append(device_id)
                response.success()
            else:
                response.failure(f"Failed to create device: {response.status_code}")
        
        # Create 1-3 test geofences per user
        num_geofences = random.randint(1, 3)
        
        for i in range(num_geofences):
            # Generate random polygon around Berlin
            center_lat = 52.520008 + random.uniform(-0.1, 0.1)
            center_lng = 13.404954 + random.uniform(-0.1, 0.1)
            size = random.uniform(0.01, 0.05)
            
            geofence_data = {
                "name": f"Load Test Geofence {i}",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [center_lng - size, center_lat - size],
                        [center_lng - size, center_lat + size],
                        [center_lng + size, center_lat + size],
                        [center_lng + size, center_lat - size],
                        [center_lng - size, center_lat - size]
                    ]]
                },
                "trigger_type": random.choice(["enter", "exit", "both"]),
                "metadata": {
                    "test": True,
                    "load_test_id": self.user_id
                }
            }
            
            response = self.client.post(
                "/api/v1/geofences",
                json=geofence_data,
                headers=self.headers,
                catch_response=True
            )
            
            if response.status_code == 201:
                geofence_id = response.json().get("id")
                if geofence_id:
                    self.geofence_ids.append(geofence_id)
                response.success()
            else:
                response.failure(f"Failed to create geofence: {response.status_code}")

    @task(20)
    def update_device_location(self):
        """High frequency task: Update device locations."""
        if not self.device_ids:
            return
        
        device_id = random.choice(self.device_ids)
        
        # Generate random location around Berlin
        location_data = {
            "latitude": 52.520008 + random.uniform(-0.05, 0.05),
            "longitude": 13.404954 + random.uniform(-0.05, 0.05),
            "timestamp": "2025-07-16T12:00:00Z",
            "accuracy": random.uniform(1.0, 10.0),
            "speed": random.uniform(0, 50),
            "heading": random.uniform(0, 360)
        }
        
        response = self.client.put(
            f"/api/v1/devices/{device_id}/location",
            json=location_data,
            headers=self.headers,
            name="/api/v1/devices/[id]/location"
        )

    @task(10)
    def get_devices_list(self):
        """Medium frequency task: Get user's devices."""
        response = self.client.get(
            "/api/v1/devices",
            headers=self.headers
        )

    @task(8)
    def find_nearby_devices(self):
        """Medium frequency task: Find nearby devices."""
        params = {
            "latitude": 52.520008 + random.uniform(-0.02, 0.02),
            "longitude": 13.404954 + random.uniform(-0.02, 0.02),
            "radius_meters": random.randint(500, 5000)
        }
        
        response = self.client.get(
            "/api/v1/devices/nearby",
            params=params,
            headers=self.headers
        )

    @task(5)
    def get_geofences_list(self):
        """Lower frequency task: Get user's geofences."""
        response = self.client.get(
            "/api/v1/geofences",
            headers=self.headers
        )

    @task(6)
    def check_geofence_status(self):
        """Medium frequency task: Check geofence triggers."""
        if not self.geofence_ids:
            return
        
        geofence_id = random.choice(self.geofence_ids)
        
        response = self.client.get(
            f"/api/v1/geofences/{geofence_id}",
            headers=self.headers,
            name="/api/v1/geofences/[id]"
        )

    @task(3)
    def optimize_route(self):
        """Lower frequency task: Route optimization."""
        # Generate random waypoints around Berlin
        waypoints = []
        for _ in range(random.randint(2, 5)):
            waypoints.append({
                "latitude": 52.520008 + random.uniform(-0.03, 0.03),
                "longitude": 13.404954 + random.uniform(-0.03, 0.03)
            })
        
        route_data = {
            "start_location": waypoints[0],
            "end_location": waypoints[-1],
            "waypoints": waypoints[1:-1] if len(waypoints) > 2 else [],
            "optimization_type": random.choice(["shortest_time", "shortest_distance"]),
            "constraints": {
                "max_distance_km": 50,
                "vehicle_type": "car"
            }
        }
        
        response = self.client.post(
            "/api/v1/routes/optimize",
            json=route_data,
            headers=self.headers
        )

    @task(2)
    def get_recommendations(self):
        """Lower frequency task: Get location recommendations."""
        location_data = {
            "latitude": 52.520008 + random.uniform(-0.02, 0.02),
            "longitude": 13.404954 + random.uniform(-0.02, 0.02),
            "radius_km": random.randint(1, 5),
            "categories": random.choice([
                ["restaurant"],
                ["hotel"],
                ["shopping"],
                ["tourist_attraction"],
                ["restaurant", "shopping"]
            ])
        }
        
        response = self.client.post(
            "/api/v1/recommendations/nearby",
            json=location_data,
            headers=self.headers
        )

    @task(4)
    def get_device_trajectory(self):
        """Medium frequency task: Get device trajectory."""
        if not self.device_ids:
            return
        
        device_id = random.choice(self.device_ids)
        
        response = self.client.get(
            f"/api/v1/devices/{device_id}/trajectory",
            params={"hours": random.choice([1, 6, 24])},
            headers=self.headers,
            name="/api/v1/devices/[id]/trajectory"
        )

    @task(1)
    def get_monitoring_health(self):
        """Low frequency task: Check system health."""
        response = self.client.get("/api/v1/monitoring/health")

    @task(1)
    def batch_location_update(self):
        """Low frequency task: Batch update device locations."""
        if not self.device_ids:
            return
        
        # Update multiple devices at once
        updates = []
        num_updates = min(len(self.device_ids), random.randint(1, 3))
        
        for device_id in random.sample(self.device_ids, num_updates):
            updates.append({
                "device_id": device_id,
                "latitude": 52.520008 + random.uniform(-0.05, 0.05),
                "longitude": 13.404954 + random.uniform(-0.05, 0.05),
                "timestamp": "2025-07-16T12:00:00Z",
                "accuracy": random.uniform(1.0, 10.0)
            })
        
        batch_data = {"updates": updates}
        
        response = self.client.post(
            "/api/v1/devices/batch-location-update",
            json=batch_data,
            headers=self.headers
        )

    def on_stop(self):
        """Clean up test data when user stops."""
        # Delete test devices
        for device_id in self.device_ids:
            self.client.delete(
                f"/api/v1/devices/{device_id}",
                headers=self.headers,
                catch_response=True
            )
        
        # Delete test geofences
        for geofence_id in self.geofence_ids:
            self.client.delete(
                f"/api/v1/geofences/{geofence_id}",
                headers=self.headers,
                catch_response=True
            )


class AdminUser(HttpUser):
    """Simulated admin user for testing admin endpoints."""
    
    wait_time = between(5, 15)  # Longer wait times for admin operations
    weight = 1  # Lower weight - fewer admin users
    
    def on_start(self):
        """Set up admin session."""
        self.headers = {
            "X-API-Key": "admin-api-key",
            "Authorization": "Bearer admin-token",
            "Content-Type": "application/json"
        }

    @task(5)
    def get_system_status(self):
        """Monitor system status."""
        response = self.client.get(
            "/api/v1/monitoring/system/status",
            headers=self.headers
        )

    @task(3)
    def get_performance_metrics(self):
        """Check performance metrics."""
        response = self.client.get(
            "/api/v1/monitoring/performance",
            headers=self.headers
        )

    @task(2)
    def get_error_summary(self):
        """Check error rates."""
        response = self.client.get(
            "/api/v1/monitoring/errors/summary",
            headers=self.headers
        )

    @task(1)
    def get_monitoring_dashboard(self):
        """Get comprehensive dashboard data."""
        response = self.client.get(
            "/api/v1/monitoring/dashboard",
            headers=self.headers
        )

    @task(1)
    def get_prometheus_metrics(self):
        """Get Prometheus metrics."""
        response = self.client.get("/api/v1/monitoring/metrics")


class SpikeUser(HttpUser):
    """User class for spike testing scenarios."""
    
    wait_time = between(0.1, 0.5)  # Very short wait times for spike testing
    weight = 0  # Not included in normal load testing
    
    def on_start(self):
        """Set up spike test session."""
        self.headers = {
            "X-API-Key": "spike-test-key",
            "Content-Type": "application/json"
        }

    @task
    def rapid_location_updates(self):
        """Rapid location updates to test rate limiting."""
        device_id = "spike-test-device"
        
        location_data = {
            "latitude": 52.520008 + random.uniform(-0.01, 0.01),
            "longitude": 13.404954 + random.uniform(-0.01, 0.01),
            "timestamp": "2025-07-16T12:00:00Z"
        }
        
        response = self.client.put(
            f"/api/v1/devices/{device_id}/location",
            json=location_data,
            headers=self.headers,
            catch_response=True
        )
        
        # Expect rate limiting after too many requests
        if response.status_code == 429:
            response.success()  # This is expected behavior
        elif response.status_code == 200:
            response.success()
        else:
            response.failure(f"Unexpected status: {response.status_code}")


# Custom test scenarios for specific load patterns
def create_user_classes():
    """Create different user classes for various testing scenarios."""
    
    class MobileAppUser(GeospatialAPIUser):
        """Simulates mobile app usage patterns."""
        weight = 3
        
        @task(30)
        def frequent_location_updates(self):
            """Mobile apps update location frequently."""
            self.update_device_location()
        
        @task(5)
        def check_nearby_places(self):
            """Users frequently check nearby places."""
            self.get_recommendations()
    
    class FleetManagementUser(GeospatialAPIUser):
        """Simulates fleet management system usage."""
        weight = 2
        
        @task(25)
        def track_fleet_vehicles(self):
            """Fleet systems track many vehicles."""
            self.update_device_location()
        
        @task(15)
        def monitor_geofences(self):
            """Fleet systems monitor geofence violations."""
            self.check_geofence_status()
        
        @task(10)
        def optimize_delivery_routes(self):
            """Fleet systems optimize routes frequently."""
            self.optimize_route()
    
    class DeliveryAppUser(GeospatialAPIUser):
        """Simulates delivery app usage patterns."""
        weight = 2
        
        @task(20)
        def track_delivery_location(self):
            """Delivery tracking updates."""
            self.update_device_location()
        
        @task(15)
        def calculate_delivery_routes(self):
            """Route calculation for deliveries."""
            self.optimize_route()
        
        @task(10)
        def find_nearby_restaurants(self):
            """Find nearby delivery options."""
            self.get_recommendations()
    
    return [MobileAppUser, FleetManagementUser, DeliveryAppUser]


# Load testing configurations
class LoadTestConfig:
    """Configuration for different load testing scenarios."""
    
    # Light load - normal operation
    LIGHT_LOAD = {
        "users": 50,
        "spawn_rate": 2,
        "run_time": "5m"
    }
    
    # Medium load - busy periods
    MEDIUM_LOAD = {
        "users": 200,
        "spawn_rate": 5,
        "run_time": "10m"
    }
    
    # Heavy load - peak traffic
    HEAVY_LOAD = {
        "users": 500,
        "spawn_rate": 10,
        "run_time": "15m"
    }
    
    # Spike test - sudden traffic increase
    SPIKE_TEST = {
        "users": 1000,
        "spawn_rate": 50,
        "run_time": "3m"
    }
    
    # Stress test - beyond normal capacity
    STRESS_TEST = {
        "users": 1500,
        "spawn_rate": 20,
        "run_time": "20m"
    }