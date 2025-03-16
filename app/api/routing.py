"""
Route Optimization API Endpoints
Provides REST API for route planning, TSP/VRP solving, and navigation services.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.services.route_service import route_service
from app.schemas.routing import (
    DirectionsRequest, DirectionsResponse,
    RouteOptimizationRequest, RouteOptimizationResponse,
    VehicleRoutingRequest, VehicleRoutingResponse,
    DistanceMatrixRequest, DistanceMatrixResponse,
    BatchRouteRequest, BatchRouteResponse,
    SavedRoute, RouteAnalytics, RouteComparison,
    TransportMode, OptimizationObjective
)

router = APIRouter()


@router.post("/directions", response_model=DirectionsResponse)
async def get_directions(
    request: DirectionsRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Get point-to-point directions between two locations.
    
    - **origin**: Starting waypoint with coordinates
    - **destination**: Ending waypoint with coordinates  
    - **mode**: Transportation mode (driving, walking, cycling, truck)
    - **alternatives**: Whether to return alternative routes
    - **avoid_traffic**: Consider real-time traffic data
    - **departure_time**: Optional departure time for traffic-aware routing
    
    Returns optimized route with turn-by-turn navigation instructions.
    """
    try:
        response = await route_service.get_directions(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating directions: {str(e)}"
        )


@router.post("/optimize", response_model=RouteOptimizationResponse)
async def optimize_route(
    request: RouteOptimizationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Solve the Traveling Salesman Problem (TSP) for multi-stop route optimization.
    
    - **waypoints**: List of stops to visit (2-100 locations)
    - **start_point**: Optional fixed starting location
    - **end_point**: Optional fixed ending location
    - **objective**: Optimization goal (distance, time, fuel, cost)
    - **vehicle**: Vehicle specifications and constraints
    - **return_to_start**: Whether to return to the starting point
    
    Returns the optimal order to visit waypoints with minimum travel cost.
    """
    if len(request.waypoints) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 waypoints required for optimization"
        )
    
    if len(request.waypoints) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 waypoints allowed per optimization request"
        )
    
    try:
        response = await route_service.optimize_route(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error optimizing route: {str(e)}"
        )


@router.post("/vehicle-routing", response_model=VehicleRoutingResponse)
async def solve_vehicle_routing(
    request: VehicleRoutingRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Solve the Vehicle Routing Problem (VRP) for multiple vehicles.
    
    Optimally assigns waypoints to vehicles and creates efficient routes
    for each vehicle starting and ending at the depot.
    
    - **waypoints**: Locations to visit (2-500 locations)
    - **vehicles**: Fleet specifications (1-10 vehicles)
    - **depot**: Starting and ending point for all vehicles
    - **objective**: Optimization objective
    - **constraints**: Route and vehicle constraints
    - **balance_loads**: Whether to balance workload across vehicles
    
    Returns optimized routes for each vehicle with load assignments.
    """
    if len(request.waypoints) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 waypoints required for VRP"
        )
    
    if len(request.waypoints) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 500 waypoints allowed per VRP request"
        )
    
    if len(request.vehicles) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 vehicles allowed per VRP request"
        )
    
    try:
        response = await route_service.solve_vehicle_routing(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error solving vehicle routing: {str(e)}"
        )


@router.post("/distance-matrix", response_model=DistanceMatrixResponse)
async def calculate_distance_matrix(
    request: DistanceMatrixRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Calculate distance and time matrix between multiple origins and destinations.
    
    - **origins**: Starting locations (1-25 locations)
    - **destinations**: Ending locations (1-25 locations)
    - **mode**: Transportation mode
    - **departure_time**: Optional departure time for traffic-aware calculations
    
    Returns distance and duration between each origin-destination pair.
    Useful for optimization algorithms and logistics planning.
    """
    if len(request.origins) > 25:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 25 origins allowed"
        )
    
    if len(request.destinations) > 25:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 25 destinations allowed"
        )
    
    try:
        response = await route_service.calculate_distance_matrix(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating distance matrix: {str(e)}"
        )


@router.post("/batch", response_model=BatchRouteResponse)
async def process_batch_routes(
    request: BatchRouteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Process multiple route requests in batch for improved efficiency.
    
    - **requests**: List of direction requests (1-100 requests)
    - **priority**: Processing priority level
    - **callback_url**: Optional webhook URL for completion notification
    
    Returns batch processing status and results when available.
    Useful for processing large numbers of routes efficiently.
    """
    if len(request.requests) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 requests allowed per batch"
        )
    
    try:
        # For now, process synchronously (can be enhanced with background processing)
        batch_id = f"batch_{current_user.id}_{int(datetime.utcnow().timestamp())}"
        results = []
        completed = 0
        failed = 0
        
        for direction_request in request.requests:
            try:
                result = await route_service.get_directions(direction_request)
                results.append(result)
                completed += 1
            except Exception:
                failed += 1
        
        return BatchRouteResponse(
            batch_id=batch_id,
            total_requests=len(request.requests),
            completed=completed,
            failed=failed,
            results=results,
            status="completed"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing batch routes: {str(e)}"
        )


@router.get("/analytics/compare")
async def compare_routes(
    route_a_waypoints: str = Query(..., description="Comma-separated lat,lon pairs for route A"),
    route_b_waypoints: str = Query(..., description="Comma-separated lat,lon pairs for route B"),
    mode: TransportMode = Query(TransportMode.DRIVING),
    current_user: User = Depends(get_current_user)
):
    """
    Compare two different routes and provide analytics.
    
    Analyzes distance, time, and efficiency differences between two route options.
    
    Format for waypoints: "lat1,lon1;lat2,lon2;lat3,lon3"
    """
    try:
        # Parse waypoints
        def parse_waypoints(waypoint_str: str):
            points = []
            for point_str in waypoint_str.split(';'):
                lat, lon = map(float, point_str.split(','))
                points.append(Waypoint(latitude=lat, longitude=lon))
            return points
        
        waypoints_a = parse_waypoints(route_a_waypoints)
        waypoints_b = parse_waypoints(route_b_waypoints)
        
        if len(waypoints_a) < 2 or len(waypoints_b) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each route must have at least 2 waypoints"
            )
        
        # Get routes
        route_a = await route_service._get_osrm_route(waypoints_a, mode)
        route_b = await route_service._get_osrm_route(waypoints_b, mode)
        
        if not route_a or not route_b:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Could not calculate one or both routes"
            )
        
        # Calculate analytics
        analytics_a = RouteAnalytics(
            route_id="route_a",
            total_distance_meters=route_a.total_distance_meters,
            total_duration_seconds=route_a.total_duration_seconds,
            average_speed_ms=route_a.total_distance_meters / route_a.total_duration_seconds if route_a.total_duration_seconds > 0 else 0,
            efficiency_score=0.8  # Placeholder
        )
        
        analytics_b = RouteAnalytics(
            route_id="route_b",
            total_distance_meters=route_b.total_distance_meters,
            total_duration_seconds=route_b.total_duration_seconds,
            average_speed_ms=route_b.total_distance_meters / route_b.total_duration_seconds if route_b.total_duration_seconds > 0 else 0,
            efficiency_score=0.8  # Placeholder
        )
        
        # Calculate differences
        distance_diff = ((route_b.total_distance_meters - route_a.total_distance_meters) / route_a.total_distance_meters * 100) if route_a.total_distance_meters > 0 else 0
        time_diff = ((route_b.total_duration_seconds - route_a.total_duration_seconds) / route_a.total_duration_seconds * 100) if route_a.total_duration_seconds > 0 else 0
        
        # Determine recommendation
        recommendation = "route_a"
        if route_b.total_duration_seconds < route_a.total_duration_seconds:
            recommendation = "route_b"
        elif abs(time_diff) < 5:  # Less than 5% difference
            recommendation = "equivalent"
        
        return RouteComparison(
            route_a=analytics_a,
            route_b=analytics_b,
            distance_difference_percent=distance_diff,
            time_difference_percent=time_diff,
            recommendation=recommendation
        )
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid waypoint format. Use 'lat1,lon1;lat2,lon2;...'"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error comparing routes: {str(e)}"
        )


@router.get("/modes")
async def get_transport_modes():
    """
    Get available transportation modes and their characteristics.
    
    Returns information about supported routing modes including
    speed profiles, constraints, and use cases.
    """
    modes = {
        "driving": {
            "name": "Driving",
            "description": "Car/automobile routing with road network",
            "average_speed_kmh": 50,
            "max_distance_km": 10000,
            "supports_traffic": True,
            "supports_tolls": True
        },
        "walking": {
            "name": "Walking",
            "description": "Pedestrian routing on walkways and roads",
            "average_speed_kmh": 5,
            "max_distance_km": 50,
            "supports_traffic": False,
            "supports_tolls": False
        },
        "cycling": {
            "name": "Cycling", 
            "description": "Bicycle routing on bike lanes and roads",
            "average_speed_kmh": 15,
            "max_distance_km": 200,
            "supports_traffic": False,
            "supports_tolls": False
        },
        "truck": {
            "name": "Truck",
            "description": "Heavy vehicle routing with restrictions",
            "average_speed_kmh": 45,
            "max_distance_km": 5000,
            "supports_traffic": True,
            "supports_tolls": True
        }
    }
    
    return {
        "available_modes": list(modes.keys()),
        "mode_details": modes,
        "optimization_objectives": [obj.value for obj in OptimizationObjective]
    }


@router.get("/health")
async def routing_health_check():
    """
    Check health status of routing services and external APIs.
    
    Returns status of OSRM service and internal routing capabilities.
    """
    try:
        # Test OSRM connectivity
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{route_service.osrm_base_url}/route/v1/driving/13.388860,52.517037;13.397634,52.529407", timeout=5) as response:
                osrm_status = "healthy" if response.status == 200 else "degraded"
    except Exception:
        osrm_status = "unavailable"
    
    return {
        "status": "healthy",
        "services": {
            "osrm": osrm_status,
            "tsp_solver": "healthy",
            "vrp_solver": "healthy",
            "distance_matrix": "healthy"
        },
        "capabilities": {
            "max_waypoints_tsp": 100,
            "max_waypoints_vrp": 500,
            "max_vehicles_vrp": 10,
            "cache_enabled": True
        }
    }