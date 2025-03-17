"""
Spatial accuracy tests for geospatial operations.
"""

import pytest
import math
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import transform
import pyproj
from functools import partial


class TestSpatialAccuracy:
    """Test spatial calculations for accuracy and precision."""

    def test_distance_calculation_accuracy(self):
        """Test distance calculations against known values."""
        # Test case: Distance between Berlin center and Brandenburg Gate
        # Known approximate distance: 2.5 km
        berlin_center = (52.520008, 13.404954)
        brandenburg_gate = (52.516275, 13.377704)
        
        calculated_distance = self._haversine_distance(
            berlin_center[0], berlin_center[1],
            brandenburg_gate[0], brandenburg_gate[1]
        )
        
        # Allow 50m tolerance for accuracy
        expected_distance = 2500  # meters
        assert abs(calculated_distance - expected_distance) < 50

    def test_point_in_polygon_accuracy(self):
        """Test point-in-polygon calculations with various scenarios."""
        # Create a square polygon around Berlin center
        berlin_square = Polygon([
            (13.3, 52.5),   # SW
            (13.3, 52.55),  # NW
            (13.5, 52.55),  # NE
            (13.5, 52.5),   # SE
            (13.3, 52.5)    # Close
        ])
        
        # Test points
        inside_point = Point(13.4, 52.52)     # Clearly inside
        outside_point = Point(13.6, 52.6)     # Clearly outside
        boundary_point = Point(13.3, 52.52)   # On boundary
        
        assert berlin_square.contains(inside_point)
        assert not berlin_square.contains(outside_point)
        assert berlin_square.touches(boundary_point) or berlin_square.contains(boundary_point)

    def test_buffer_calculation_accuracy(self):
        """Test buffer calculations for circular geofences."""
        # Create a point at Berlin center
        center_point = Point(13.404954, 52.520008)
        
        # Create 1km buffer
        buffer_distance_degrees = self._meters_to_degrees(1000, 52.520008)
        buffered_area = center_point.buffer(buffer_distance_degrees)
        
        # Calculate actual area and compare to expected
        # Transform to projected coordinate system for accurate area calculation
        transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        buffered_projected = transform(transformer.transform, buffered_area)
        
        area_m2 = buffered_projected.area
        expected_area_m2 = math.pi * (1000 ** 2)  # π * r²
        
        # Allow 5% tolerance for projection differences
        tolerance = expected_area_m2 * 0.05
        assert abs(area_m2 - expected_area_m2) < tolerance

    def test_coordinate_system_transformations(self):
        """Test coordinate system transformations for accuracy."""
        # Original point in WGS84 (EPSG:4326)
        original_lat, original_lng = 52.520008, 13.404954
        
        # Transform to Web Mercator (EPSG:3857) and back
        transformer_to_mercator = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        transformer_to_wgs84 = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
        
        # Forward transformation
        x, y = transformer_to_mercator.transform(original_lng, original_lat)
        
        # Backward transformation
        lng_back, lat_back = transformer_to_wgs84.transform(x, y)
        
        # Check accuracy (should be very close to original)
        assert abs(lat_back - original_lat) < 0.000001
        assert abs(lng_back - original_lng) < 0.000001

    def test_polygon_area_calculation(self):
        """Test polygon area calculations in different coordinate systems."""
        # Create a 1km x 1km square in Berlin
        # Using approximate coordinate differences for 1km at Berlin's latitude
        lat_diff = 1000 / 111320  # 1 degree latitude ≈ 111,320 meters
        lng_diff = 1000 / (111320 * math.cos(math.radians(52.52)))  # Adjusted for latitude
        
        square_polygon = Polygon([
            (13.404954, 52.520008),
            (13.404954 + lng_diff, 52.520008),
            (13.404954 + lng_diff, 52.520008 + lat_diff),
            (13.404954, 52.520008 + lat_diff),
            (13.404954, 52.520008)
        ])
        
        # Transform to projected coordinate system for accurate area calculation
        transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        square_projected = transform(transformer.transform, square_polygon)
        
        area_m2 = square_projected.area
        expected_area_m2 = 1000 * 1000  # 1km²
        
        # Allow 2% tolerance
        tolerance = expected_area_m2 * 0.02
        assert abs(area_m2 - expected_area_m2) < tolerance

    def test_line_length_calculation(self):
        """Test line length calculations for route accuracy."""
        # Create a line from Berlin center to Brandenburg Gate
        route_line = LineString([
            (13.404954, 52.520008),  # Berlin center
            (13.377704, 52.516275)   # Brandenburg Gate
        ])
        
        # Transform to projected coordinate system for accurate length calculation
        transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        route_projected = transform(transformer.transform, route_line)
        
        length_m = route_projected.length
        expected_length_m = 2500  # Approximate straight-line distance
        
        # Allow 100m tolerance
        assert abs(length_m - expected_length_m) < 100

    def test_spatial_index_accuracy(self):
        """Test spatial index queries for accuracy."""
        # Create multiple test points around Berlin
        test_points = [
            Point(13.404954, 52.520008),  # Berlin center
            Point(13.377704, 52.516275),  # Brandenburg Gate
            Point(13.425293, 52.500342),  # Alexanderplatz
            Point(13.373688, 52.508533),  # Potsdamer Platz
        ]
        
        # Create search area around Berlin center
        search_center = Point(13.404954, 52.520008)
        search_radius_degrees = self._meters_to_degrees(3000, 52.520008)  # 3km radius
        search_area = search_center.buffer(search_radius_degrees)
        
        # Find points within search area
        points_in_area = [point for point in test_points if search_area.contains(point)]
        
        # All test points should be within 3km of Berlin center
        assert len(points_in_area) == len(test_points)

    def test_geofence_precision_boundaries(self):
        """Test precision at geofence boundaries."""
        # Create a precise polygon boundary
        precise_polygon = Polygon([
            (13.4, 52.52),
            (13.41, 52.52),
            (13.41, 52.53),
            (13.4, 52.53),
            (13.4, 52.52)
        ])
        
        # Test points very close to boundary (1 meter precision)
        boundary_lat = 52.52
        boundary_lng = 13.4
        
        # Point just inside (move 0.5m east)
        inside_offset = 0.5 / (111320 * math.cos(math.radians(boundary_lat)))
        inside_point = Point(boundary_lng + inside_offset, boundary_lat)
        
        # Point just outside (move 0.5m west)
        outside_point = Point(boundary_lng - inside_offset, boundary_lat)
        
        assert precise_polygon.contains(inside_point)
        assert not precise_polygon.contains(outside_point)

    def test_large_scale_accuracy(self):
        """Test accuracy with large geographical areas."""
        # Create a large polygon covering multiple countries
        europe_polygon = Polygon([
            (-10, 35),  # Western Iberia
            (30, 35),   # Eastern Mediterranean
            (30, 70),   # Northern Scandinavia
            (-10, 70),  # Northern British Isles
            (-10, 35)   # Close
        ])
        
        # Test points
        berlin = Point(13.404954, 52.520008)
        madrid = Point(-3.7038, 40.4168)
        oslo = Point(10.7522, 59.9139)
        
        assert europe_polygon.contains(berlin)
        assert europe_polygon.contains(madrid)
        assert europe_polygon.contains(oslo)

    def test_small_scale_precision(self):
        """Test precision with very small geographical areas."""
        # Create a 10m x 10m square (building-level precision)
        building_size_degrees = 10 / 111320  # 10 meters in degrees
        
        building_polygon = Polygon([
            (13.404954, 52.520008),
            (13.404954 + building_size_degrees, 52.520008),
            (13.404954 + building_size_degrees, 52.520008 + building_size_degrees),
            (13.404954, 52.520008 + building_size_degrees),
            (13.404954, 52.520008)
        ])
        
        # Point at center of building
        center_point = Point(
            13.404954 + building_size_degrees/2,
            52.520008 + building_size_degrees/2
        )
        
        # Point just outside building
        outside_point = Point(
            13.404954 + building_size_degrees * 1.1,
            52.520008
        )
        
        assert building_polygon.contains(center_point)
        assert not building_polygon.contains(outside_point)

    def test_route_optimization_accuracy(self):
        """Test accuracy of route optimization calculations."""
        # Define test points for TSP problem
        waypoints = [
            (13.404954, 52.520008),  # Berlin center
            (13.377704, 52.516275),  # Brandenburg Gate  
            (13.425293, 52.500342),  # Alexanderplatz
            (13.373688, 52.508533),  # Potsdamer Platz
        ]
        
        # Calculate distances between all point pairs
        distances = {}
        for i, point1 in enumerate(waypoints):
            for j, point2 in enumerate(waypoints):
                if i != j:
                    dist = self._haversine_distance(
                        point1[1], point1[0], point2[1], point2[0]
                    )
                    distances[(i, j)] = dist
        
        # Verify triangle inequality (basic sanity check for TSP)
        for i in range(len(waypoints)):
            for j in range(len(waypoints)):
                for k in range(len(waypoints)):
                    if i != j and j != k and i != k:
                        direct = distances.get((i, k), float('inf'))
                        via_j = distances.get((i, j), 0) + distances.get((j, k), 0)
                        assert direct <= via_j * 1.1  # Allow small tolerance for measurement

    def _haversine_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate Haversine distance between two points in meters."""
        R = 6371000  # Earth's radius in meters
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)
        
        a = (math.sin(delta_lat/2) * math.sin(delta_lat/2) +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lng/2) * math.sin(delta_lng/2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c

    def _meters_to_degrees(self, meters: float, latitude: float) -> float:
        """Convert meters to degrees at given latitude."""
        # Approximate conversion (more accurate methods exist)
        lat_deg_per_meter = 1 / 111320
        lng_deg_per_meter = 1 / (111320 * math.cos(math.radians(latitude)))
        
        # Use average for circular buffer
        return meters * math.sqrt((lat_deg_per_meter ** 2 + lng_deg_per_meter ** 2) / 2)

    def test_coordinate_precision_limits(self):
        """Test precision limits of coordinate storage and calculations."""
        # Test with maximum precision coordinates
        high_precision_point = Point(13.404954123456789, 52.520008987654321)
        
        # Round trip through string conversion (simulating database storage)
        point_str = f"POINT({high_precision_point.x} {high_precision_point.y})"
        from shapely import wkt
        recovered_point = wkt.loads(point_str)
        
        # Check precision loss
        precision_loss_x = abs(high_precision_point.x - recovered_point.x)
        precision_loss_y = abs(high_precision_point.y - recovered_point.y)
        
        # Should maintain reasonable precision (sub-meter accuracy)
        assert precision_loss_x < 0.00001  # ~1m at this longitude
        assert precision_loss_y < 0.00001  # ~1m at this latitude

    def test_projection_accuracy_comparison(self):
        """Test accuracy differences between coordinate projections."""
        # Original point
        original = Point(13.404954, 52.520008)
        
        # Test different projections
        projections = [
            "EPSG:3857",  # Web Mercator
            "EPSG:32633", # UTM Zone 33N (appropriate for Berlin)
            "EPSG:4326"   # WGS84 (no projection)
        ]
        
        areas = []
        for proj in projections:
            if proj == "EPSG:4326":
                # Skip projection for WGS84
                buffer_area = original.buffer(0.01)  # Approximate buffer
            else:
                transformer = pyproj.Transformer.from_crs("EPSG:4326", proj, always_xy=True)
                projected_point = transform(transformer.transform, original)
                buffer_area = projected_point.buffer(1000)  # 1km buffer
                
                # Transform back for comparison
                back_transformer = pyproj.Transformer.from_crs(proj, "EPSG:4326", always_xy=True)
                buffer_area = transform(back_transformer.transform, buffer_area)
            
            areas.append(buffer_area.area)
        
        # Areas should be similar (within reasonable tolerance)
        if len(areas) > 1:
            max_area = max(areas[:-1])  # Exclude WGS84 area
            min_area = min(areas[:-1])
            relative_difference = (max_area - min_area) / min_area
            assert relative_difference < 0.1  # 10% tolerance