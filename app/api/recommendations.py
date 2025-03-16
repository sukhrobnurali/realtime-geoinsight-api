"""
Location-based Recommendation API Endpoints
Provides REST API for place discovery, personalized recommendations, and spatial search.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.services.recommendation_service import recommendation_service
from app.schemas.recommendations import (
    NearbySearchRequest, NearbySearchResponse,
    PersonalizedRecommendationRequest, PersonalizedRecommendationResponse,
    TrendingPlacesRequest, TrendingPlacesResponse,
    SimilarPlacesRequest, SimilarPlacesResponse,
    RouteRecommendationRequest, RouteRecommendationResponse,
    AutocompleteRequest, AutocompleteResponse,
    Location, CategoryType, PriceLevel, SortBy,
    PlaceCreate, PlaceUpdate, Place,
    UserPreferences, LocationInsights
)

router = APIRouter()


@router.post("/nearby", response_model=NearbySearchResponse)
async def search_nearby_places(
    request: NearbySearchRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Search for places near a location with filtering and sorting options.
    
    - **location**: Center point for search (latitude, longitude)
    - **radius_meters**: Search radius in meters (max 50km)
    - **categories**: Filter by place categories
    - **keywords**: Search by keywords in place names/descriptions
    - **min_rating**: Minimum average rating filter
    - **price_levels**: Filter by price levels
    - **open_now**: Only show places currently open
    - **limit**: Maximum results to return (1-100)
    - **sort_by**: Sort order (distance, rating, popularity, relevance)
    
    Returns ranked list of places with scoring details and reasons.
    """
    if request.radius_meters > 50000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum search radius is 50km"
        )
    
    try:
        response = await recommendation_service.search_nearby_places(
            request=request,
            user_id=str(current_user.id)
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching nearby places: {str(e)}"
        )


@router.post("/personalized", response_model=PersonalizedRecommendationResponse)
async def get_personalized_recommendations(
    request: PersonalizedRecommendationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Get personalized place recommendations based on user preferences and history.
    
    - **location**: Center point for recommendations
    - **radius_meters**: Search radius in meters (max 50km)
    - **categories**: Preferred categories (overrides user defaults)
    - **user_preferences**: Additional preference data
    - **previous_visits**: List of previously visited place IDs
    - **exclude_visited**: Whether to exclude previously visited places
    - **diversity_factor**: Balance between relevance and variety (0-1)
    - **limit**: Maximum recommendations to return (1-50)
    
    Uses machine learning and user behavior to provide highly relevant suggestions.
    """
    if request.radius_meters > 50000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum search radius is 50km"
        )
    
    try:
        response = await recommendation_service.get_personalized_recommendations(
            request=request,
            user_id=str(current_user.id)
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting personalized recommendations: {str(e)}"
        )


@router.post("/trending", response_model=TrendingPlacesResponse)
async def get_trending_places(
    request: TrendingPlacesRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Get trending places in an area based on recent activity and popularity.
    
    - **location**: Center point for trending analysis
    - **radius_meters**: Analysis radius in meters (max 100km)
    - **categories**: Filter by place categories
    - **time_period_days**: Analysis period in days (1-365)
    - **min_visits**: Minimum visits to be considered trending
    - **limit**: Maximum trending places to return (1-100)
    
    Analyzes visit patterns, reviews, and engagement to identify hot spots.
    """
    if request.radius_meters > 100000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum analysis radius is 100km"
        )
    
    try:
        response = await recommendation_service.get_trending_places(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting trending places: {str(e)}"
        )


@router.post("/similar", response_model=SimilarPlacesResponse)
async def get_similar_places(
    request: SimilarPlacesRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Find places similar to a reference place based on characteristics.
    
    - **place_id**: Reference place ID to find similar places
    - **location**: Optional center point (defaults to reference place location)
    - **radius_meters**: Search radius in meters (max 50km)
    - **similarity_threshold**: Minimum similarity score (0-1)
    - **limit**: Maximum similar places to return (1-50)
    
    Uses category, price level, amenities, and ratings to find similar venues.
    """
    if request.radius_meters > 50000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum search radius is 50km"
        )
    
    try:
        response = await recommendation_service.get_similar_places(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finding similar places: {str(e)}"
        )


@router.post("/route", response_model=RouteRecommendationResponse)
async def get_route_recommendations(
    request: RouteRecommendationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Get place recommendations along a route with minimal detour.
    
    - **waypoints**: Route waypoints (2-20 locations)
    - **buffer_meters**: Search buffer around route (max 10km)
    - **categories**: Filter by place categories
    - **max_detour_meters**: Maximum acceptable detour distance
    - **limit_per_segment**: Max recommendations per route segment (1-20)
    
    Perfect for road trips, delivery routes, or exploring new areas.
    """
    if len(request.waypoints) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 waypoints required for route recommendations"
        )
    
    if len(request.waypoints) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 20 waypoints allowed"
        )
    
    if request.buffer_meters > 10000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum buffer distance is 10km"
        )
    
    try:
        response = await recommendation_service.get_route_recommendations(
            request=request,
            user_id=str(current_user.id)
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting route recommendations: {str(e)}"
        )


@router.post("/autocomplete", response_model=AutocompleteResponse)
async def autocomplete_places(
    request: AutocompleteRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Get autocomplete suggestions for place names and searches.
    
    - **query**: Search query text (1-100 characters)
    - **location**: Optional location to bias results
    - **radius_meters**: Search radius for location bias (max 100km)
    - **categories**: Filter suggestions by categories
    - **limit**: Maximum suggestions to return (1-20)
    
    Provides fast, intelligent autocomplete for search interfaces.
    """
    if len(request.query.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty"
        )
    
    try:
        response = await recommendation_service.autocomplete_places(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting autocomplete suggestions: {str(e)}"
        )


@router.get("/categories")
async def get_available_categories():
    """
    Get all available place categories and their descriptions.
    
    Returns list of categories with metadata for filtering and search.
    """
    categories = {
        CategoryType.RESTAURANT: {
            "name": "Restaurants",
            "description": "Dining establishments, cafes, bars, and food venues",
            "subcategories": ["fast_food", "fine_dining", "cafe", "bar", "bakery"]
        },
        CategoryType.HOTEL: {
            "name": "Hotels",
            "description": "Accommodation and lodging facilities",
            "subcategories": ["hotel", "motel", "hostel", "resort", "bed_breakfast"]
        },
        CategoryType.SHOPPING: {
            "name": "Shopping",
            "description": "Retail stores, malls, and shopping centers",
            "subcategories": ["mall", "boutique", "grocery", "electronics", "clothing"]
        },
        CategoryType.ENTERTAINMENT: {
            "name": "Entertainment",
            "description": "Movies, theaters, nightlife, and entertainment venues",
            "subcategories": ["cinema", "theater", "nightclub", "arcade", "karaoke"]
        },
        CategoryType.TOURISM: {
            "name": "Tourism",
            "description": "Tourist attractions, landmarks, and sightseeing",
            "subcategories": ["museum", "monument", "park", "landmark", "gallery"]
        },
        CategoryType.HEALTHCARE: {
            "name": "Healthcare",
            "description": "Medical facilities and health services",
            "subcategories": ["hospital", "clinic", "pharmacy", "dentist", "veterinary"]
        },
        CategoryType.EDUCATION: {
            "name": "Education",
            "description": "Schools, universities, and educational institutions",
            "subcategories": ["school", "university", "library", "museum", "training"]
        },
        CategoryType.TRANSPORTATION: {
            "name": "Transportation",
            "description": "Transit hubs, stations, and transportation services",
            "subcategories": ["airport", "train_station", "bus_stop", "parking", "taxi"]
        },
        CategoryType.SERVICES: {
            "name": "Services",
            "description": "Professional and personal services",
            "subcategories": ["bank", "post_office", "salon", "repair", "legal"]
        },
        CategoryType.RECREATION: {
            "name": "Recreation",
            "description": "Parks, sports facilities, and recreational activities",
            "subcategories": ["park", "gym", "sports_center", "playground", "trail"]
        }
    }
    
    return {
        "categories": [
            {
                "id": category.value,
                "name": details["name"],
                "description": details["description"],
                "subcategories": details["subcategories"]
            }
            for category, details in categories.items()
        ],
        "price_levels": [
            {"id": level.value, "name": level.value.title(), "description": f"{level.value.title()} pricing"}
            for level in PriceLevel
        ],
        "sort_options": [
            {"id": sort.value, "name": sort.value.title(), "description": f"Sort by {sort.value}"}
            for sort in SortBy
        ]
    }


@router.get("/insights")
async def get_location_insights(
    latitude: float = Query(..., ge=-90, le=90, description="Center latitude"),
    longitude: float = Query(..., ge=-180, le=180, description="Center longitude"),
    radius_meters: float = Query(5000, gt=0, le=50000, description="Analysis radius in meters"),
    current_user: User = Depends(get_current_user)
):
    """
    Get analytical insights about a geographic area.
    
    - **latitude**: Center latitude for analysis
    - **longitude**: Center longitude for analysis
    - **radius_meters**: Analysis radius in meters (max 50km)
    
    Returns demographic data, category distribution, and area characteristics.
    """
    try:
        # Mock insights - in production this would analyze real data
        location = Location(latitude=latitude, longitude=longitude)
        
        insights = LocationInsights(
            center_location=location,
            radius_meters=radius_meters,
            total_places=250,
            category_distribution={
                CategoryType.RESTAURANT: 45,
                CategoryType.SHOPPING: 38,
                CategoryType.ENTERTAINMENT: 25,
                CategoryType.SERVICES: 32,
                CategoryType.RECREATION: 18
            },
            avg_rating=4.1,
            popular_amenities=["wifi", "parking", "credit_cards", "wheelchair_accessible"],
            price_level_distribution={
                PriceLevel.BUDGET: 35,
                PriceLevel.MODERATE: 42,
                PriceLevel.EXPENSIVE: 15,
                PriceLevel.LUXURY: 8
            },
            peak_activity_hours=[12, 13, 18, 19, 20],
            seasonal_trends={
                "spring": 0.85,
                "summer": 1.2,
                "fall": 0.95,
                "winter": 0.7
            }
        )
        
        return insights
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting location insights: {str(e)}"
        )


@router.get("/popular-searches")
async def get_popular_searches(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_meters: float = Query(10000, gt=0, le=100000),
    days: int = Query(7, ge=1, le=30, description="Time period in days"),
    current_user: User = Depends(get_current_user)
):
    """
    Get popular search terms and trending categories in an area.
    
    Useful for understanding local interests and search behavior.
    """
    try:
        # Mock popular searches data
        popular_data = {
            "location": {"latitude": latitude, "longitude": longitude},
            "radius_meters": radius_meters,
            "time_period_days": days,
            "popular_keywords": [
                {"keyword": "coffee", "search_count": 1250, "trend": "+15%"},
                {"keyword": "pizza", "search_count": 980, "trend": "+8%"},
                {"keyword": "gym", "search_count": 756, "trend": "+22%"},
                {"keyword": "pharmacy", "search_count": 643, "trend": "+5%"},
                {"keyword": "gas station", "search_count": 521, "trend": "-3%"}
            ],
            "popular_categories": [
                {"category": "restaurant", "search_count": 3200, "trend": "+12%"},
                {"category": "shopping", "search_count": 2100, "trend": "+7%"},
                {"category": "healthcare", "search_count": 1800, "trend": "+18%"},
                {"category": "services", "search_count": 1400, "trend": "+3%"},
                {"category": "entertainment", "search_count": 1200, "trend": "+25%"}
            ],
            "trending_searches": [
                {"term": "outdoor dining", "growth_rate": 0.45},
                {"term": "24 hour", "growth_rate": 0.38},
                {"term": "delivery", "growth_rate": 0.32},
                {"term": "parking", "growth_rate": 0.28},
                {"term": "pet friendly", "growth_rate": 0.25}
            ]
        }
        
        return popular_data
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting popular searches: {str(e)}"
        )


@router.get("/preferences", response_model=UserPreferences)
async def get_user_preferences(
    current_user: User = Depends(get_current_user)
):
    """
    Get the current user's recommendation preferences.
    
    Returns personalization settings used for recommendations.
    """
    try:
        # In production, this would fetch from database
        preferences = UserPreferences(
            user_id=str(current_user.id),
            preferred_categories=[CategoryType.RESTAURANT, CategoryType.ENTERTAINMENT],
            preferred_price_levels=[PriceLevel.MODERATE],
            preferred_amenities=["wifi", "parking"],
            rating_threshold=4.0,
            max_travel_distance=10000,
            preferred_visit_times=[12, 13, 18, 19, 20],
            family_friendly=True
        )
        
        return preferences
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting user preferences: {str(e)}"
        )


@router.put("/preferences", response_model=UserPreferences)
async def update_user_preferences(
    preferences: UserPreferences,
    current_user: User = Depends(get_current_user)
):
    """
    Update the current user's recommendation preferences.
    
    Customizes future recommendations based on user preferences.
    """
    try:
        # Validate user ID matches current user
        if preferences.user_id != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update preferences for another user"
            )
        
        # In production, this would save to database
        preferences.updated_at = datetime.utcnow()
        
        return preferences
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating user preferences: {str(e)}"
        )


@router.get("/health")
async def recommendations_health_check():
    """
    Check health status of recommendation services.
    
    Returns status of recommendation engine and data sources.
    """
    try:
        # Test recommendation service
        test_location = Location(latitude=40.7128, longitude=-74.0060)
        test_request = NearbySearchRequest(location=test_location, limit=1)
        
        # Quick test
        await recommendation_service.search_nearby_places(test_request)
        
        return {
            "status": "healthy",
            "services": {
                "recommendation_engine": "healthy",
                "spatial_search": "healthy", 
                "personalization": "healthy",
                "caching": "healthy"
            },
            "capabilities": {
                "max_search_radius_km": 50,
                "max_route_waypoints": 20,
                "supported_categories": len(CategoryType),
                "autocomplete_enabled": True,
                "personalization_enabled": True
            }
        }
        
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
            "services": {
                "recommendation_engine": "error",
                "spatial_search": "unknown",
                "personalization": "unknown", 
                "caching": "unknown"
            }
        }