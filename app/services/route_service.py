"""
Route Optimization Service
Handles route planning, TSP solving, VRP optimization, and external routing API integration.
"""

import asyncio
import hashlib
import json
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import aiohttp
import numpy as np
from scipy.spatial.distance import pdist, squareform
from scipy.optimize import minimize
import uuid

from app.config import settings
from app.schemas.routing import (
    DirectionsRequest, DirectionsResponse, RouteOptimizationRequest, 
    RouteOptimizationResponse, VehicleRoutingRequest, VehicleRoutingResponse,
    DistanceMatrixRequest, DistanceMatrixResponse, Waypoint, Route, RouteLeg,
    RouteStep, OptimizedRoute, VehicleRoute, DistanceMatrixElement,
    TransportMode, OptimizationObjective, RouteCacheKey, SavedRoute
)
from app.services.redis_client import redis_client


class RouteService:
    """Service for route optimization and navigation."""
    
    def __init__(self):
        self.osrm_base_url = "http://router.project-osrm.org"
        self.cache_ttl = 3600  # 1 hour cache
        
    async def get_directions(self, request: DirectionsRequest) -> DirectionsResponse:
        """Get point-to-point directions."""
        request_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        # Check cache first
        cache_key = self._generate_directions_cache_key(request)
        cached_result = await self._get_cached_route(cache_key)
        if cached_result:
            return DirectionsResponse(
                routes=[cached_result],
                request_id=request_id,
                computation_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
        
        # Get route from external service
        route = await self._get_osrm_route(
            [request.origin, request.destination],
            request.mode,
            request.alternatives
        )
        
        # Cache the result
        await self._cache_route(cache_key, route)
        
        computation_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return DirectionsResponse(
            routes=[route] if route else [],
            request_id=request_id,
            computation_time_ms=computation_time
        )
    
    async def optimize_route(self, request: RouteOptimizationRequest) -> RouteOptimizationResponse:
        """Solve Traveling Salesman Problem for route optimization."""
        request_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        # Get distance matrix between all waypoints
        waypoints = request.waypoints.copy()
        if request.start_point:
            waypoints.insert(0, request.start_point)
        if request.end_point and request.end_point != request.start_point:
            waypoints.append(request.end_point)
        
        distance_matrix = await self._calculate_distance_matrix(waypoints, request.vehicle.vehicle_type)
        
        # Solve TSP
        if len(waypoints) <= 2:
            optimal_order = list(range(len(waypoints)))
        else:
            optimal_order = await self._solve_tsp(
                distance_matrix, 
                request.objective,
                request.return_to_start
            )
        
        # Build optimized route
        ordered_waypoints = [waypoints[i] for i in optimal_order]
        optimized_route_data = await self._get_osrm_route(
            ordered_waypoints, 
            request.vehicle.vehicle_type
        )
        
        # Calculate original distance for comparison
        original_distance = await self._calculate_total_distance(waypoints, request.vehicle.vehicle_type)
        optimized_distance = optimized_route_data.total_distance_meters if optimized_route_data else 0
        
        savings_percent = ((original_distance - optimized_distance) / original_distance * 100) if original_distance > 0 else 0
        
        computation_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        optimized_route = OptimizedRoute(
            route=optimized_route_data,
            waypoint_order=optimal_order,
            optimization_quality=max(0, min(1, savings_percent / 100)),
            computation_time_ms=computation_time
        )
        
        return RouteOptimizationResponse(
            optimized_route=optimized_route,
            original_distance=original_distance,
            optimized_distance=optimized_distance,
            savings_percent=max(0, savings_percent),
            request_id=request_id
        )
    
    async def solve_vehicle_routing(self, request: VehicleRoutingRequest) -> VehicleRoutingResponse:
        """Solve Vehicle Routing Problem for multiple vehicles."""
        request_id = str(uuid.uuid4())
        
        # Calculate distance matrix
        all_points = [request.depot] + request.waypoints
        distance_matrix = await self._calculate_distance_matrix(all_points, request.vehicles[0].vehicle_type)
        
        # Implement simple VRP solver (can be enhanced with OR-Tools)
        vehicle_routes = await self._solve_vrp_simple(
            distance_matrix,
            request.waypoints,
            request.vehicles,
            request.depot,
            request.constraints
        )
        
        total_distance = sum(vr.route.total_distance_meters for vr in vehicle_routes)
        total_duration = sum(vr.route.total_duration_seconds for vr in vehicle_routes)
        
        return VehicleRoutingResponse(
            vehicle_routes=vehicle_routes,
            total_distance=total_distance,
            total_duration=total_duration,
            request_id=request_id
        )
    
    async def calculate_distance_matrix(self, request: DistanceMatrixRequest) -> DistanceMatrixResponse:
        """Calculate distance/time matrix between origins and destinations."""
        request_id = str(uuid.uuid4())
        
        # Use OSRM table service for distance matrix
        matrix_data = await self._get_osrm_table(
            request.origins + request.destinations,
            len(request.origins),
            len(request.destinations),
            request.mode
        )
        
        return DistanceMatrixResponse(
            origin_addresses=[f"{wp.latitude},{wp.longitude}" for wp in request.origins],
            destination_addresses=[f"{wp.latitude},{wp.longitude}" for wp in request.destinations],
            rows=matrix_data,
            request_id=request_id
        )
    
    async def _get_osrm_route(
        self, 
        waypoints: List[Waypoint], 
        mode: TransportMode,
        alternatives: bool = False
    ) -> Optional[Route]:
        """Get route from OSRM service."""
        try:
            # Build coordinates string
            coords = ";".join([f"{wp.longitude},{wp.latitude}" for wp in waypoints])
            
            # Map transport mode to OSRM profile
            profile_map = {
                TransportMode.DRIVING: "driving",
                TransportMode.WALKING: "foot",
                TransportMode.CYCLING: "bike",
                TransportMode.TRUCK: "driving"  # Use driving for truck, can enhance later
            }
            profile = profile_map.get(mode, "driving")
            
            url = f"{self.osrm_base_url}/route/v1/{profile}/{coords}"
            params = {
                "overview": "full",
                "geometries": "geojson",
                "steps": "true",
                "alternatives": "true" if alternatives else "false"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == "Ok" and data.get("routes"):
                            return self._parse_osrm_route(data["routes"][0], waypoints)
            
            return None
            
        except Exception as e:
            print(f"Error getting OSRM route: {e}")
            return None
    
    def _parse_osrm_route(self, osrm_route: Dict, waypoints: List[Waypoint]) -> Route:
        """Parse OSRM response into our Route format."""
        legs = []
        
        for i, leg in enumerate(osrm_route.get("legs", [])):
            steps = []
            for step in leg.get("steps", []):
                steps.append(RouteStep(
                    instruction=step.get("maneuver", {}).get("instruction", ""),
                    distance_meters=step.get("distance", 0),
                    duration_seconds=step.get("duration", 0),
                    maneuver=step.get("maneuver", {}).get("type", ""),
                    street_name=step.get("name", "")
                ))
            
            route_leg = RouteLeg(
                start_waypoint=waypoints[i],
                end_waypoint=waypoints[i + 1],
                distance_meters=leg.get("distance", 0),
                duration_seconds=leg.get("duration", 0),
                steps=steps
            )
            legs.append(route_leg)
        
        return Route(
            legs=legs,
            total_distance_meters=osrm_route.get("distance", 0),
            total_duration_seconds=osrm_route.get("duration", 0),
            polyline=self._encode_polyline(osrm_route.get("geometry", {}).get("coordinates", []))
        )
    
    async def _get_osrm_table(
        self, 
        points: List[Waypoint], 
        origins_count: int,
        destinations_count: int,
        mode: TransportMode
    ) -> List[List[DistanceMatrixElement]]:
        """Get distance matrix from OSRM table service."""
        try:
            coords = ";".join([f"{wp.longitude},{wp.latitude}" for wp in points])
            
            profile_map = {
                TransportMode.DRIVING: "driving",
                TransportMode.WALKING: "foot", 
                TransportMode.CYCLING: "bike",
                TransportMode.TRUCK: "driving"
            }
            profile = profile_map.get(mode, "driving")
            
            sources = ";".join([str(i) for i in range(origins_count)])
            destinations = ";".join([str(i) for i in range(origins_count, origins_count + destinations_count)])
            
            url = f"{self.osrm_base_url}/table/v1/{profile}/{coords}"
            params = {
                "sources": sources,
                "destinations": destinations
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == "Ok":
                            durations = data.get("durations", [])
                            distances = data.get("distances", [])
                            
                            rows = []
                            for i in range(origins_count):
                                row = []
                                for j in range(destinations_count):
                                    element = DistanceMatrixElement(
                                        distance_meters=distances[i][j] if distances else None,
                                        duration_seconds=durations[i][j] if durations else None,
                                        status="OK"
                                    )
                                    row.append(element)
                                rows.append(row)
                            return rows
            
            # Return empty matrix on failure
            return [[DistanceMatrixElement(status="NOT_FOUND") for _ in range(destinations_count)] 
                   for _ in range(origins_count)]
            
        except Exception as e:
            print(f"Error getting OSRM table: {e}")
            return [[DistanceMatrixElement(status="NOT_FOUND") for _ in range(destinations_count)] 
                   for _ in range(origins_count)]
    
    async def _solve_tsp(
        self, 
        distance_matrix: np.ndarray, 
        objective: OptimizationObjective,
        return_to_start: bool = False
    ) -> List[int]:
        """Solve TSP using nearest neighbor heuristic with 2-opt improvement."""
        n = len(distance_matrix)
        if n <= 2:
            return list(range(n))
        
        # Start with nearest neighbor solution
        tour = self._nearest_neighbor_tsp(distance_matrix)
        
        # Improve with 2-opt
        tour = self._two_opt_improvement(tour, distance_matrix)
        
        if not return_to_start and len(tour) > 2:
            # Remove return to start for open tour
            tour = tour[:-1]
        
        return tour
    
    def _nearest_neighbor_tsp(self, distance_matrix: np.ndarray) -> List[int]:
        """Nearest neighbor heuristic for TSP."""
        n = len(distance_matrix)
        unvisited = set(range(1, n))
        tour = [0]
        current = 0
        
        while unvisited:
            nearest = min(unvisited, key=lambda x: distance_matrix[current][x])
            tour.append(nearest)
            unvisited.remove(nearest)
            current = nearest
        
        tour.append(0)  # Return to start
        return tour
    
    def _two_opt_improvement(self, tour: List[int], distance_matrix: np.ndarray) -> List[int]:
        """Improve TSP solution with 2-opt."""
        best_tour = tour[:]
        best_distance = self._calculate_tour_distance(tour, distance_matrix)
        improved = True
        
        while improved:
            improved = False
            for i in range(1, len(tour) - 2):
                for j in range(i + 1, len(tour)):
                    if j - i == 1:
                        continue
                    
                    new_tour = tour[:]
                    new_tour[i:j] = tour[i:j][::-1]
                    new_distance = self._calculate_tour_distance(new_tour, distance_matrix)
                    
                    if new_distance < best_distance:
                        best_tour = new_tour
                        best_distance = new_distance
                        tour = new_tour
                        improved = True
        
        return best_tour
    
    def _calculate_tour_distance(self, tour: List[int], distance_matrix: np.ndarray) -> float:
        """Calculate total distance of a tour."""
        total = 0
        for i in range(len(tour) - 1):
            total += distance_matrix[tour[i]][tour[i + 1]]
        return total
    
    async def _calculate_distance_matrix(
        self, 
        waypoints: List[Waypoint], 
        mode: TransportMode
    ) -> np.ndarray:
        """Calculate distance matrix between waypoints."""
        n = len(waypoints)
        matrix = np.zeros((n, n))
        
        # Use simplified distance calculation for now
        coords = np.array([[wp.latitude, wp.longitude] for wp in waypoints])
        distances = squareform(pdist(coords, metric='euclidean'))
        
        # Convert to approximate meters (rough conversion)
        distances = distances * 111000  # degrees to meters approximation
        
        return distances
    
    async def _calculate_total_distance(
        self, 
        waypoints: List[Waypoint], 
        mode: TransportMode
    ) -> float:
        """Calculate total distance visiting waypoints in order."""
        if len(waypoints) < 2:
            return 0
        
        total = 0
        for i in range(len(waypoints) - 1):
            # Simple haversine distance approximation
            lat1, lon1 = waypoints[i].latitude, waypoints[i].longitude
            lat2, lon2 = waypoints[i + 1].latitude, waypoints[i + 1].longitude
            total += self._haversine_distance(lat1, lon1, lat2, lon2)
        
        return total
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate haversine distance between two points."""
        R = 6371000  # Earth radius in meters
        
        lat1_rad = np.radians(lat1)
        lat2_rad = np.radians(lat2)
        delta_lat = np.radians(lat2 - lat1)
        delta_lon = np.radians(lon2 - lon1)
        
        a = (np.sin(delta_lat / 2) ** 2 + 
             np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lon / 2) ** 2)
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
        
        return R * c
    
    async def _solve_vrp_simple(
        self,
        distance_matrix: np.ndarray,
        waypoints: List[Waypoint],
        vehicles: List,
        depot: Waypoint,
        constraints
    ) -> List[VehicleRoute]:
        """Simple VRP solver using nearest neighbor."""
        vehicle_routes = []
        unassigned = set(range(1, len(waypoints) + 1))  # Skip depot at index 0
        
        for i, vehicle in enumerate(vehicles):
            if not unassigned:
                break
                
            # Build route for this vehicle
            route_waypoints = [depot]
            current_load = 0
            current_pos = 0
            vehicle_unassigned = unassigned.copy()
            
            while vehicle_unassigned:
                # Find nearest unassigned waypoint
                nearest = min(
                    vehicle_unassigned,
                    key=lambda x: distance_matrix[current_pos][x]
                )
                
                route_waypoints.append(waypoints[nearest - 1])
                vehicle_unassigned.remove(nearest)
                unassigned.remove(nearest)
                current_pos = nearest
                
                # Simple capacity constraint
                if len(route_waypoints) >= 10:  # Max 10 stops per vehicle
                    break
            
            route_waypoints.append(depot)  # Return to depot
            
            # Create route
            if len(route_waypoints) > 2:
                route_data = await self._get_osrm_route(route_waypoints, vehicle.vehicle_type)
                if route_data:
                    vehicle_routes.append(VehicleRoute(
                        vehicle_id=i,
                        route=route_data,
                        load_utilization=0.5,  # Placeholder
                        assigned_waypoints=list(range(1, len(route_waypoints) - 1))
                    ))
        
        return vehicle_routes
    
    def _encode_polyline(self, coordinates: List[List[float]]) -> str:
        """Encode coordinates as polyline (simplified version)."""
        if not coordinates:
            return ""
        
        # This is a simplified polyline encoding
        # In production, use a proper polyline encoding library
        return json.dumps(coordinates)
    
    def _generate_directions_cache_key(self, request: DirectionsRequest) -> str:
        """Generate cache key for directions request."""
        key_data = {
            "origin": f"{request.origin.latitude},{request.origin.longitude}",
            "destination": f"{request.destination.latitude},{request.destination.longitude}",
            "mode": request.mode.value,
            "avoid_traffic": request.avoid_traffic
        }
        return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
    
    async def _get_cached_route(self, cache_key: str) -> Optional[Route]:
        """Get cached route from Redis."""
        try:
            cached_data = await redis_client.get(f"route:{cache_key}")
            if cached_data:
                return Route.model_validate_json(cached_data)
        except Exception:
            pass
        return None
    
    async def _cache_route(self, cache_key: str, route: Route):
        """Cache route in Redis."""
        try:
            await redis_client.setex(
                f"route:{cache_key}",
                self.cache_ttl,
                route.model_dump_json()
            )
        except Exception:
            pass


# Singleton instance
route_service = RouteService()