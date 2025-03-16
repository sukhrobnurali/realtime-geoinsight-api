"""
Location-based Recommendation Schemas
Defines data models for spatial recommendations and place discovery.
"""

from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, time
from pydantic import BaseModel, Field, validator
from enum import Enum


class CategoryType(str, Enum):
    """Categories for location-based recommendations."""
    RESTAURANT = "restaurant"
    HOTEL = "hotel"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    TOURISM = "tourism"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    TRANSPORTATION = "transportation"
    SERVICES = "services"
    RECREATION = "recreation"
    BUSINESS = "business"
    AUTOMOTIVE = "automotive"


class PriceLevel(str, Enum):
    """Price level indicators."""
    FREE = "free"
    BUDGET = "budget"
    MODERATE = "moderate"
    EXPENSIVE = "expensive"
    LUXURY = "luxury"


class SortBy(str, Enum):
    """Sorting options for recommendations."""
    DISTANCE = "distance"
    RATING = "rating"
    POPULARITY = "popularity"
    PRICE = "price"
    RELEVANCE = "relevance"
    NEWEST = "newest"


# Base Location and Place Models
class Location(BaseModel):
    """Basic location with coordinates."""
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")


class PlaceHours(BaseModel):
    """Operating hours for a place."""
    day_of_week: int = Field(..., ge=0, le=6, description="Day of week (0=Monday, 6=Sunday)")
    open_time: Optional[time] = Field(None, description="Opening time")
    close_time: Optional[time] = Field(None, description="Closing time")
    is_closed: bool = Field(False, description="Closed all day")


class PlaceContact(BaseModel):
    """Contact information for a place."""
    phone: Optional[str] = Field(None)
    email: Optional[str] = Field(None)
    website: Optional[str] = Field(None)
    social_media: Optional[Dict[str, str]] = Field(default_factory=dict)


class PlaceReview(BaseModel):
    """User review for a place."""
    user_id: Optional[str] = Field(None)
    username: Optional[str] = Field(None)
    rating: float = Field(..., ge=1, le=5, description="Rating from 1 to 5")
    comment: Optional[str] = Field(None, max_length=1000)
    helpful_votes: int = Field(0, ge=0)
    created_at: datetime
    verified: bool = Field(False)


class Place(BaseModel):
    """A place or point of interest."""
    id: str = Field(..., description="Unique place identifier")
    name: str = Field(..., description="Place name")
    description: Optional[str] = Field(None, max_length=2000)
    location: Location
    address: Optional[str] = Field(None)
    category: CategoryType
    subcategory: Optional[str] = Field(None, description="Specific subcategory")
    
    # Ratings and popularity
    rating: Optional[float] = Field(None, ge=1, le=5, description="Average rating")
    review_count: int = Field(0, ge=0)
    popularity_score: float = Field(0, ge=0, le=1, description="Popularity score 0-1")
    
    # Business information
    price_level: Optional[PriceLevel] = Field(None)
    contact: Optional[PlaceContact] = Field(None)
    hours: Optional[List[PlaceHours]] = Field(None)
    
    # Additional attributes
    amenities: List[str] = Field(default_factory=list, description="Available amenities")
    photos: List[str] = Field(default_factory=list, description="Photo URLs")
    tags: List[str] = Field(default_factory=list, description="Searchable tags")
    
    # Metadata
    verified: bool = Field(False, description="Verified business")
    created_at: datetime
    updated_at: datetime
    
    # Calculated fields (populated by recommendation service)
    distance_meters: Optional[float] = Field(None, ge=0)
    relevance_score: Optional[float] = Field(None, ge=0, le=1)


# Recommendation Requests
class NearbySearchRequest(BaseModel):
    """Request for nearby places search."""
    location: Location
    radius_meters: float = Field(1000, gt=0, le=50000, description="Search radius in meters")
    categories: Optional[List[CategoryType]] = Field(None, description="Filter by categories")
    subcategories: Optional[List[str]] = Field(None, description="Filter by subcategories")
    keywords: Optional[str] = Field(None, description="Search keywords")
    min_rating: Optional[float] = Field(None, ge=1, le=5)
    price_levels: Optional[List[PriceLevel]] = Field(None)
    open_now: Optional[bool] = Field(None, description="Only show places open now")
    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")
    sort_by: SortBy = Field(SortBy.DISTANCE)


class PersonalizedRecommendationRequest(BaseModel):
    """Request for personalized recommendations."""
    location: Location
    radius_meters: float = Field(5000, gt=0, le=50000)
    categories: Optional[List[CategoryType]] = Field(None)
    user_preferences: Optional[Dict[str, Any]] = Field(None, description="User preference data")
    previous_visits: Optional[List[str]] = Field(None, description="Previously visited place IDs")
    exclude_visited: bool = Field(True, description="Exclude previously visited places")
    diversity_factor: float = Field(0.5, ge=0, le=1, description="Diversity vs relevance balance")
    limit: int = Field(10, ge=1, le=50)


class TrendingPlacesRequest(BaseModel):
    """Request for trending places in an area."""
    location: Location
    radius_meters: float = Field(10000, gt=0, le=100000)
    categories: Optional[List[CategoryType]] = Field(None)
    time_period_days: int = Field(7, ge=1, le=365, description="Trending period in days")
    min_visits: int = Field(10, ge=1, description="Minimum visits to be considered trending")
    limit: int = Field(20, ge=1, le=100)


class SimilarPlacesRequest(BaseModel):
    """Request for places similar to a given place."""
    place_id: str = Field(..., description="Reference place ID")
    location: Optional[Location] = Field(None, description="Search around this location")
    radius_meters: float = Field(10000, gt=0, le=50000)
    similarity_threshold: float = Field(0.7, ge=0, le=1, description="Minimum similarity score")
    limit: int = Field(10, ge=1, le=50)


class RouteRecommendationRequest(BaseModel):
    """Request for recommendations along a route."""
    waypoints: List[Location] = Field(..., min_items=2, max_items=20)
    buffer_meters: float = Field(2000, gt=0, le=10000, description="Search buffer around route")
    categories: Optional[List[CategoryType]] = Field(None)
    max_detour_meters: float = Field(5000, gt=0, description="Maximum detour distance")
    limit_per_segment: int = Field(5, ge=1, le=20, description="Max recommendations per route segment")


# Recommendation Responses
class RecommendationScore(BaseModel):
    """Detailed scoring for a recommendation."""
    overall_score: float = Field(..., ge=0, le=1)
    distance_score: float = Field(..., ge=0, le=1)
    rating_score: float = Field(..., ge=0, le=1)
    popularity_score: float = Field(..., ge=0, le=1)
    relevance_score: float = Field(..., ge=0, le=1)
    personalization_score: Optional[float] = Field(None, ge=0, le=1)


class PlaceRecommendation(BaseModel):
    """A recommended place with scoring details."""
    place: Place
    score: RecommendationScore
    reasons: List[str] = Field(default_factory=list, description="Why this was recommended")
    visit_suggestion: Optional[str] = Field(None, description="Suggested visit details")


class NearbySearchResponse(BaseModel):
    """Response for nearby places search."""
    query_location: Location
    radius_meters: float
    total_found: int
    recommendations: List[PlaceRecommendation]
    search_metadata: Dict[str, Any] = Field(default_factory=dict)
    request_id: str


class PersonalizedRecommendationResponse(BaseModel):
    """Response for personalized recommendations."""
    user_id: str
    query_location: Location
    recommendations: List[PlaceRecommendation]
    personalization_factors: Dict[str, float] = Field(default_factory=dict)
    request_id: str


class TrendingPlacesResponse(BaseModel):
    """Response for trending places."""
    query_location: Location
    time_period_days: int
    trending_places: List[PlaceRecommendation]
    trend_analysis: Dict[str, Any] = Field(default_factory=dict)
    request_id: str


class SimilarPlacesResponse(BaseModel):
    """Response for similar places."""
    reference_place_id: str
    similar_places: List[PlaceRecommendation]
    similarity_factors: Dict[str, float] = Field(default_factory=dict)
    request_id: str


class RouteRecommendationResponse(BaseModel):
    """Response for route-based recommendations."""
    route_waypoints: List[Location]
    route_recommendations: List[PlaceRecommendation]
    segment_breakdown: Dict[str, List[PlaceRecommendation]] = Field(default_factory=dict)
    total_detour_meters: float
    request_id: str


# Analytics and Insights
class PlaceAnalytics(BaseModel):
    """Analytics data for a place."""
    place_id: str
    views: int = Field(0, ge=0)
    clicks: int = Field(0, ge=0)
    visits: int = Field(0, ge=0)
    recommendations_shown: int = Field(0, ge=0)
    avg_visit_duration_minutes: Optional[float] = Field(None, ge=0)
    peak_hours: List[int] = Field(default_factory=list, description="Peak hours 0-23")
    visitor_demographics: Dict[str, Any] = Field(default_factory=dict)
    conversion_rate: float = Field(0, ge=0, le=1)


class LocationInsights(BaseModel):
    """Insights for a geographic area."""
    center_location: Location
    radius_meters: float
    total_places: int
    category_distribution: Dict[CategoryType, int]
    avg_rating: float
    popular_amenities: List[str]
    price_level_distribution: Dict[PriceLevel, int]
    peak_activity_hours: List[int]
    seasonal_trends: Dict[str, float] = Field(default_factory=dict)


class UserPreferences(BaseModel):
    """User preference profile for personalization."""
    user_id: str
    preferred_categories: List[CategoryType] = Field(default_factory=list)
    preferred_price_levels: List[PriceLevel] = Field(default_factory=list)
    preferred_amenities: List[str] = Field(default_factory=list)
    rating_threshold: float = Field(3.0, ge=1, le=5)
    max_travel_distance: float = Field(10000, gt=0)
    
    # Behavioral data
    visit_history: List[str] = Field(default_factory=list, description="Visited place IDs")
    favorite_places: List[str] = Field(default_factory=list)
    avoided_places: List[str] = Field(default_factory=list)
    search_history: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Time preferences
    preferred_visit_times: List[int] = Field(default_factory=list, description="Preferred hours 0-23")
    weekend_preferences: Optional[Dict[str, Any]] = Field(None)
    
    # Social preferences
    group_size_preference: Optional[int] = Field(None, ge=1)
    family_friendly: Optional[bool] = Field(None)
    
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Place Management
class PlaceCreate(BaseModel):
    """Schema for creating a new place."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    location: Location
    address: Optional[str] = Field(None, max_length=500)
    category: CategoryType
    subcategory: Optional[str] = Field(None, max_length=100)
    price_level: Optional[PriceLevel] = Field(None)
    contact: Optional[PlaceContact] = Field(None)
    hours: Optional[List[PlaceHours]] = Field(None)
    amenities: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class PlaceUpdate(BaseModel):
    """Schema for updating a place."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    address: Optional[str] = Field(None, max_length=500)
    category: Optional[CategoryType] = Field(None)
    subcategory: Optional[str] = Field(None, max_length=100)
    price_level: Optional[PriceLevel] = Field(None)
    contact: Optional[PlaceContact] = Field(None)
    hours: Optional[List[PlaceHours]] = Field(None)
    amenities: Optional[List[str]] = Field(None)
    tags: Optional[List[str]] = Field(None)


# Feedback and Reviews
class ReviewCreate(BaseModel):
    """Schema for creating a place review."""
    place_id: str
    rating: float = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)


class ReviewUpdate(BaseModel):
    """Schema for updating a review."""
    rating: Optional[float] = Field(None, ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)


class PlaceFeedback(BaseModel):
    """User feedback on recommendation quality."""
    place_id: str
    recommendation_id: str
    user_id: str
    feedback_type: Literal["helpful", "not_helpful", "incorrect", "visited", "saved"]
    comment: Optional[str] = Field(None, max_length=500)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Search and Discovery
class AutocompleteRequest(BaseModel):
    """Request for place name autocomplete."""
    query: str = Field(..., min_length=1, max_length=100)
    location: Optional[Location] = Field(None, description="Bias results near this location")
    radius_meters: float = Field(50000, gt=0, le=100000)
    categories: Optional[List[CategoryType]] = Field(None)
    limit: int = Field(10, ge=1, le=20)


class AutocompleteResult(BaseModel):
    """Autocomplete suggestion result."""
    place_id: str
    name: str
    address: Optional[str] = Field(None)
    category: CategoryType
    distance_meters: Optional[float] = Field(None)
    match_score: float = Field(..., ge=0, le=1)


class AutocompleteResponse(BaseModel):
    """Response for autocomplete request."""
    query: str
    suggestions: List[AutocompleteResult]
    request_id: str


class PopularSearches(BaseModel):
    """Popular search terms and categories."""
    location: Location
    radius_meters: float
    popular_keywords: List[Dict[str, Any]]
    popular_categories: List[Dict[str, Any]]
    trending_searches: List[Dict[str, Any]]
    time_period: str