"""
Routing and Route Optimization Schemas
Defines data models for route planning, optimization, and navigation.
"""

from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum


class TransportMode(str, Enum):
    """Transportation modes for routing."""
    DRIVING = "driving"
    WALKING = "walking"
    CYCLING = "cycling"
    TRUCK = "truck"


class OptimizationObjective(str, Enum):
    """Optimization objectives for route planning."""
    DISTANCE = "distance"
    TIME = "time"
    FUEL = "fuel"
    COST = "cost"


class Waypoint(BaseModel):
    """A single waypoint with coordinates and optional metadata."""
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")
    name: Optional[str] = Field(None, description="Human-readable name for the waypoint")
    address: Optional[str] = Field(None, description="Street address")
    stop_duration: Optional[int] = Field(0, description="Stop duration in seconds")
    time_window_start: Optional[datetime] = Field(None, description="Earliest arrival time")
    time_window_end: Optional[datetime] = Field(None, description="Latest arrival time")
    priority: Optional[int] = Field(1, ge=1, le=10, description="Priority level (1-10)")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class RouteConstraints(BaseModel):
    """Constraints for route optimization."""
    max_distance_meters: Optional[float] = Field(None, gt=0)
    max_duration_seconds: Optional[float] = Field(None, gt=0)
    max_stops: Optional[int] = Field(None, ge=1)
    avoid_tolls: bool = Field(False)
    avoid_highways: bool = Field(False)
    avoid_ferries: bool = Field(False)


class VehicleProfile(BaseModel):
    """Vehicle specifications for routing."""
    vehicle_type: TransportMode = Field(TransportMode.DRIVING)
    max_weight_kg: Optional[float] = Field(None, gt=0)
    max_volume_m3: Optional[float] = Field(None, gt=0)
    max_distance_per_day: Optional[float] = Field(None, gt=0)
    fuel_consumption_per_km: Optional[float] = Field(None, gt=0)
    cost_per_km: Optional[float] = Field(None, gt=0)
    speed_factor: float = Field(1.0, gt=0, le=2.0, description="Speed multiplier")


# Route Planning Requests
class DirectionsRequest(BaseModel):
    """Request for simple point-to-point directions."""
    origin: Waypoint
    destination: Waypoint
    mode: TransportMode = Field(TransportMode.DRIVING)
    alternatives: bool = Field(False, description="Return alternative routes")
    avoid_traffic: bool = Field(True, description="Avoid traffic if possible")
    departure_time: Optional[datetime] = Field(None)


class RouteOptimizationRequest(BaseModel):
    """Request for multi-stop route optimization (TSP)."""
    waypoints: List[Waypoint] = Field(..., min_items=2, max_items=100)
    start_point: Optional[Waypoint] = Field(None, description="Fixed start point")
    end_point: Optional[Waypoint] = Field(None, description="Fixed end point")
    objective: OptimizationObjective = Field(OptimizationObjective.TIME)
    vehicle: VehicleProfile = Field(default_factory=VehicleProfile)
    constraints: RouteConstraints = Field(default_factory=RouteConstraints)
    return_to_start: bool = Field(False, description="Return to starting point")


class VehicleRoutingRequest(BaseModel):
    """Request for Vehicle Routing Problem (VRP) with multiple vehicles."""
    waypoints: List[Waypoint] = Field(..., min_items=2, max_items=500)
    vehicles: List[VehicleProfile] = Field(..., min_items=1, max_items=10)
    depot: Waypoint = Field(..., description="Starting depot for all vehicles")
    objective: OptimizationObjective = Field(OptimizationObjective.TIME)
    constraints: RouteConstraints = Field(default_factory=RouteConstraints)
    balance_loads: bool = Field(True, description="Balance loads across vehicles")


class DistanceMatrixRequest(BaseModel):
    """Request for distance/time matrix calculation."""
    origins: List[Waypoint] = Field(..., min_items=1, max_items=25)
    destinations: List[Waypoint] = Field(..., min_items=1, max_items=25)
    mode: TransportMode = Field(TransportMode.DRIVING)
    departure_time: Optional[datetime] = Field(None)


# Route Responses
class RouteStep(BaseModel):
    """A single step in a route."""
    instruction: str = Field(..., description="Turn-by-turn instruction")
    distance_meters: float = Field(..., ge=0)
    duration_seconds: float = Field(..., ge=0)
    polyline: Optional[str] = Field(None, description="Encoded polyline")
    maneuver: Optional[str] = Field(None, description="Maneuver type")
    street_name: Optional[str] = Field(None)


class RouteLeg(BaseModel):
    """A leg of a route between two waypoints."""
    start_waypoint: Waypoint
    end_waypoint: Waypoint
    distance_meters: float = Field(..., ge=0)
    duration_seconds: float = Field(..., ge=0)
    steps: List[RouteStep] = Field(default_factory=list)
    polyline: Optional[str] = Field(None, description="Encoded polyline for entire leg")
    traffic_delay_seconds: Optional[float] = Field(None)


class Route(BaseModel):
    """A complete route with all legs and metadata."""
    legs: List[RouteLeg]
    total_distance_meters: float = Field(..., ge=0)
    total_duration_seconds: float = Field(..., ge=0)
    total_cost: Optional[float] = Field(None)
    polyline: Optional[str] = Field(None, description="Encoded polyline for entire route")
    bounds: Optional[Dict[str, float]] = Field(None, description="Bounding box")
    traffic_info: Optional[Dict[str, Any]] = Field(None)


class OptimizedRoute(BaseModel):
    """An optimized route with waypoint ordering."""
    route: Route
    waypoint_order: List[int] = Field(..., description="Optimized order of waypoints")
    optimization_quality: float = Field(..., ge=0, le=1, description="Quality score")
    computation_time_ms: float = Field(..., ge=0)


class DirectionsResponse(BaseModel):
    """Response for directions request."""
    routes: List[Route]
    request_id: str
    computation_time_ms: float


class RouteOptimizationResponse(BaseModel):
    """Response for route optimization."""
    optimized_route: OptimizedRoute
    original_distance: float
    optimized_distance: float
    savings_percent: float
    request_id: str


class VehicleRoute(BaseModel):
    """Route for a single vehicle in VRP."""
    vehicle_id: int
    route: Route
    load_utilization: float = Field(..., ge=0, le=1)
    assigned_waypoints: List[int]


class VehicleRoutingResponse(BaseModel):
    """Response for vehicle routing problem."""
    vehicle_routes: List[VehicleRoute]
    total_distance: float
    total_duration: float
    total_cost: Optional[float] = Field(None)
    unassigned_waypoints: List[int] = Field(default_factory=list)
    request_id: str


class DistanceMatrixElement(BaseModel):
    """Single element in distance matrix."""
    distance_meters: Optional[float] = Field(None)
    duration_seconds: Optional[float] = Field(None)
    status: Literal["OK", "NOT_FOUND", "UNREACHABLE"] = Field("OK")


class DistanceMatrixResponse(BaseModel):
    """Response for distance matrix calculation."""
    origin_addresses: List[str]
    destination_addresses: List[str]
    rows: List[List[DistanceMatrixElement]]
    request_id: str


# Route Analysis and Statistics
class RouteAnalytics(BaseModel):
    """Analytics for route performance."""
    route_id: str
    total_distance_meters: float
    total_duration_seconds: float
    average_speed_ms: float
    fuel_consumption: Optional[float] = Field(None)
    carbon_emissions_kg: Optional[float] = Field(None)
    toll_cost: Optional[float] = Field(None)
    traffic_delay_seconds: Optional[float] = Field(None)
    efficiency_score: float = Field(..., ge=0, le=1)


class RouteComparison(BaseModel):
    """Comparison between different route options."""
    route_a: RouteAnalytics
    route_b: RouteAnalytics
    distance_difference_percent: float
    time_difference_percent: float
    cost_difference_percent: Optional[float] = Field(None)
    recommendation: Literal["route_a", "route_b", "equivalent"]


# Real-time Route Updates
class TrafficIncident(BaseModel):
    """Real-time traffic incident."""
    incident_id: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    severity: Literal["low", "medium", "high", "critical"]
    type: str = Field(..., description="Accident, construction, etc.")
    description: str
    delay_minutes: Optional[int] = Field(None)
    start_time: datetime
    estimated_end_time: Optional[datetime] = Field(None)


class RouteUpdate(BaseModel):
    """Real-time route update with traffic information."""
    route_id: str
    updated_duration_seconds: float
    traffic_delay_seconds: float
    incidents: List[TrafficIncident] = Field(default_factory=list)
    alternative_route: Optional[Route] = Field(None)
    update_timestamp: datetime = Field(default_factory=datetime.utcnow)


# Route Caching and History
class RouteCacheKey(BaseModel):
    """Key for route caching."""
    origin_hash: str
    destination_hash: str
    waypoints_hash: Optional[str] = Field(None)
    mode: TransportMode
    constraints_hash: str
    
    
class SavedRoute(BaseModel):
    """A saved route for reuse."""
    id: str
    user_id: str
    name: str
    description: Optional[str] = Field(None)
    route: Route
    waypoints: List[Waypoint]
    created_at: datetime
    last_used: Optional[datetime] = Field(None)
    use_count: int = Field(0)
    is_favorite: bool = Field(False)


# Batch Processing
class BatchRouteRequest(BaseModel):
    """Request for batch route processing."""
    requests: List[DirectionsRequest] = Field(..., max_items=100)
    priority: Literal["low", "normal", "high"] = Field("normal")
    callback_url: Optional[str] = Field(None)


class BatchRouteResponse(BaseModel):
    """Response for batch processing."""
    batch_id: str
    total_requests: int
    completed: int
    failed: int
    results: List[DirectionsResponse] = Field(default_factory=list)
    status: Literal["pending", "processing", "completed", "failed"]