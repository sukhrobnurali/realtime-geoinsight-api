"""
Location-based Recommendation Service
Handles spatial search, personalized recommendations, and place discovery.
"""

import json
import math
import uuid
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_MakePoint

from app.schemas.recommendations import (
    NearbySearchRequest, NearbySearchResponse,
    PersonalizedRecommendationRequest, PersonalizedRecommendationResponse,
    TrendingPlacesRequest, TrendingPlacesResponse,
    SimilarPlacesRequest, SimilarPlacesResponse,
    RouteRecommendationRequest, RouteRecommendationResponse,
    AutocompleteRequest, AutocompleteResponse, AutocompleteResult,
    Place, PlaceRecommendation, RecommendationScore, Location,
    UserPreferences, PlaceAnalytics, LocationInsights,
    CategoryType, PriceLevel, SortBy
)
from app.services.redis_client import redis_client


class RecommendationService:
    """Service for location-based recommendations and place discovery."""
    
    def __init__(self):
        self.cache_ttl = 1800  # 30 minutes cache
        self.popularity_decay_days = 30
        
    async def search_nearby_places(
        self,
        request: NearbySearchRequest,
        user_id: Optional[str] = None
    ) -> NearbySearchResponse:
        """Search for places near a location with filtering and sorting."""
        request_id = str(uuid.uuid4())
        
        # Generate cache key
        cache_key = self._generate_search_cache_key(request, user_id)
        cached_result = await self._get_cached_recommendations(cache_key)
        
        if cached_result:
            return cached_result
        
        # Mock places data - in production this would query a places database
        mock_places = await self._get_mock_places_near_location(
            request.location,
            request.radius_meters,
            request.categories,
            request.keywords,
            request.min_rating,
            request.price_levels,
            request.open_now
        )
        
        # Calculate recommendations with scoring
        recommendations = []
        for place in mock_places:
            score = await self._calculate_recommendation_score(
                place, request.location, user_id, request
            )
            
            recommendation = PlaceRecommendation(
                place=place,
                score=score,
                reasons=self._generate_recommendation_reasons(place, score)
            )
            recommendations.append(recommendation)
        
        # Sort recommendations
        recommendations = self._sort_recommendations(recommendations, request.sort_by)
        
        # Limit results
        recommendations = recommendations[:request.limit]
        
        response = NearbySearchResponse(
            query_location=request.location,
            radius_meters=request.radius_meters,
            total_found=len(mock_places),
            recommendations=recommendations,
            search_metadata={
                "filters_applied": {
                    "categories": request.categories,
                    "min_rating": request.min_rating,
                    "price_levels": request.price_levels,
                    "open_now": request.open_now
                },
                "sort_by": request.sort_by
            },
            request_id=request_id
        )
        
        # Cache result
        await self._cache_recommendations(cache_key, response)
        
        return response
    
    async def get_personalized_recommendations(
        self,
        request: PersonalizedRecommendationRequest,
        user_id: str
    ) -> PersonalizedRecommendationResponse:
        """Get personalized recommendations based on user preferences and history."""
        request_id = str(uuid.uuid4())
        
        # Get user preferences
        user_prefs = await self._get_user_preferences(user_id)
        
        # Get base recommendations
        nearby_request = NearbySearchRequest(
            location=request.location,
            radius_meters=request.radius_meters,
            categories=request.categories or user_prefs.preferred_categories,
            limit=request.limit * 3  # Get more to filter
        )
        
        base_recommendations = await self.search_nearby_places(nearby_request, user_id)
        
        # Apply personalization
        personalized_recs = []
        for rec in base_recommendations.recommendations:
            # Skip previously visited places if requested
            if (request.exclude_visited and 
                rec.place.id in (request.previous_visits or [])):
                continue
            
            # Enhance scoring with personalization
            enhanced_score = await self._enhance_score_with_personalization(
                rec.score, rec.place, user_prefs, request
            )
            
            rec.score = enhanced_score
            rec.reasons.extend(self._generate_personalization_reasons(rec.place, user_prefs))
            
            personalized_recs.append(rec)
        
        # Apply diversity if requested
        if request.diversity_factor > 0:
            personalized_recs = self._apply_diversity_filtering(
                personalized_recs, request.diversity_factor
            )
        
        # Sort by enhanced scores and limit
        personalized_recs.sort(key=lambda x: x.score.overall_score, reverse=True)
        personalized_recs = personalized_recs[:request.limit]
        
        personalization_factors = {
            "category_match": 0.8,
            "price_preference": 0.6,
            "rating_threshold": 0.9,
            "historical_visits": 0.7
        }
        
        return PersonalizedRecommendationResponse(
            user_id=user_id,
            query_location=request.location,
            recommendations=personalized_recs,
            personalization_factors=personalization_factors,
            request_id=request_id
        )
    
    async def get_trending_places(
        self,
        request: TrendingPlacesRequest
    ) -> TrendingPlacesResponse:
        """Get trending places in an area based on recent activity."""
        request_id = str(uuid.uuid4())
        
        # Mock trending analysis - in production this would analyze real visit data
        mock_places = await self._get_mock_places_near_location(
            request.location,
            request.radius_meters,
            request.categories,
            limit=request.limit * 2
        )
        
        # Simulate trending scores
        trending_places = []
        for place in mock_places:
            # Mock trending calculation
            base_score = await self._calculate_recommendation_score(
                place, request.location, None, None
            )
            
            # Add trending boost
            trending_boost = self._calculate_trending_boost(place, request.time_period_days)
            base_score.overall_score = min(1.0, base_score.overall_score + trending_boost)
            
            recommendation = PlaceRecommendation(
                place=place,
                score=base_score,
                reasons=[f"Trending with {trending_boost:.1%} increase in visits"]
            )
            trending_places.append(recommendation)
        
        # Sort by trending score
        trending_places.sort(key=lambda x: x.score.overall_score, reverse=True)
        trending_places = trending_places[:request.limit]
        
        trend_analysis = {
            "time_period_days": request.time_period_days,
            "total_analyzed": len(mock_places),
            "trending_threshold": 0.2,
            "category_trends": self._analyze_category_trends(trending_places)
        }
        
        return TrendingPlacesResponse(
            query_location=request.location,
            time_period_days=request.time_period_days,
            trending_places=trending_places,
            trend_analysis=trend_analysis,
            request_id=request_id
        )
    
    async def get_similar_places(
        self,
        request: SimilarPlacesRequest
    ) -> SimilarPlacesResponse:
        """Find places similar to a reference place."""
        request_id = str(uuid.uuid4())
        
        # Get reference place (mock)
        reference_place = await self._get_place_by_id(request.place_id)
        if not reference_place:
            return SimilarPlacesResponse(
                reference_place_id=request.place_id,
                similar_places=[],
                similarity_factors={},
                request_id=request_id
            )
        
        # Search for candidate places
        search_location = request.location or reference_place.location
        candidates = await self._get_mock_places_near_location(
            search_location,
            request.radius_meters,
            [reference_place.category],
            limit=request.limit * 3
        )
        
        # Calculate similarity scores
        similar_places = []
        for candidate in candidates:
            if candidate.id == request.place_id:
                continue
                
            similarity_score = self._calculate_place_similarity(
                reference_place, candidate
            )
            
            if similarity_score >= request.similarity_threshold:
                score = RecommendationScore(
                    overall_score=similarity_score,
                    distance_score=0.8,
                    rating_score=candidate.rating / 5.0 if candidate.rating else 0.5,
                    popularity_score=candidate.popularity_score,
                    relevance_score=similarity_score
                )
                
                recommendation = PlaceRecommendation(
                    place=candidate,
                    score=score,
                    reasons=[f"Similar to {reference_place.name}"]
                )
                similar_places.append(recommendation)
        
        # Sort by similarity
        similar_places.sort(key=lambda x: x.score.overall_score, reverse=True)
        similar_places = similar_places[:request.limit]
        
        similarity_factors = {
            "category_match": 0.9,
            "price_similarity": 0.7,
            "amenity_overlap": 0.6,
            "rating_similarity": 0.8
        }
        
        return SimilarPlacesResponse(
            reference_place_id=request.place_id,
            similar_places=similar_places,
            similarity_factors=similarity_factors,
            request_id=request_id
        )
    
    async def get_route_recommendations(
        self,
        request: RouteRecommendationRequest,
        user_id: Optional[str] = None
    ) -> RouteRecommendationResponse:
        """Get recommendations along a route."""
        request_id = str(uuid.uuid4())
        
        all_recommendations = []
        segment_breakdown = {}
        total_detour = 0.0
        
        # Process each route segment
        for i in range(len(request.waypoints) - 1):
            start_point = request.waypoints[i]
            end_point = request.waypoints[i + 1]
            
            # Find places near this segment
            segment_center = Location(
                latitude=(start_point.latitude + end_point.latitude) / 2,
                longitude=(start_point.longitude + end_point.longitude) / 2
            )
            
            segment_places = await self._get_mock_places_near_location(
                segment_center,
                request.buffer_meters,
                request.categories,
                limit=request.limit_per_segment * 2
            )
            
            # Filter by detour distance
            segment_recommendations = []
            for place in segment_places:
                detour_distance = self._calculate_route_detour(
                    start_point, end_point, place.location
                )
                
                if detour_distance <= request.max_detour_meters:
                    score = await self._calculate_recommendation_score(
                        place, segment_center, user_id, None
                    )
                    
                    # Boost score for minimal detour
                    detour_factor = 1 - (detour_distance / request.max_detour_meters)
                    score.overall_score = min(1.0, score.overall_score * (1 + detour_factor * 0.2))
                    
                    recommendation = PlaceRecommendation(
                        place=place,
                        score=score,
                        reasons=[f"Only {detour_distance:.0f}m detour from route"]
                    )
                    segment_recommendations.append(recommendation)
                    total_detour += detour_distance
            
            # Sort and limit segment recommendations
            segment_recommendations.sort(key=lambda x: x.score.overall_score, reverse=True)
            segment_recommendations = segment_recommendations[:request.limit_per_segment]
            
            segment_key = f"segment_{i}_{i+1}"
            segment_breakdown[segment_key] = segment_recommendations
            all_recommendations.extend(segment_recommendations)
        
        # Remove duplicates and sort overall
        seen_places = set()
        unique_recommendations = []
        for rec in sorted(all_recommendations, key=lambda x: x.score.overall_score, reverse=True):
            if rec.place.id not in seen_places:
                unique_recommendations.append(rec)
                seen_places.add(rec.place.id)
        
        return RouteRecommendationResponse(
            route_waypoints=request.waypoints,
            route_recommendations=unique_recommendations,
            segment_breakdown=segment_breakdown,
            total_detour_meters=total_detour,
            request_id=request_id
        )
    
    async def autocomplete_places(
        self,
        request: AutocompleteRequest
    ) -> AutocompleteResponse:
        """Provide autocomplete suggestions for place names."""
        request_id = str(uuid.uuid4())
        
        # Mock autocomplete - in production this would use search indices
        mock_places = await self._get_mock_places_near_location(
            request.location or Location(latitude=0, longitude=0),
            request.radius_meters,
            request.categories,
            keywords=request.query,
            limit=request.limit * 3
        )
        
        suggestions = []
        for place in mock_places:
            # Calculate match score based on name similarity
            match_score = self._calculate_text_similarity(request.query.lower(), place.name.lower())
            
            if match_score > 0.3:  # Minimum match threshold
                suggestion = AutocompleteResult(
                    place_id=place.id,
                    name=place.name,
                    address=place.address,
                    category=place.category,
                    distance_meters=place.distance_meters,
                    match_score=match_score
                )
                suggestions.append(suggestion)
        
        # Sort by match score and limit
        suggestions.sort(key=lambda x: x.match_score, reverse=True)
        suggestions = suggestions[:request.limit]
        
        return AutocompleteResponse(
            query=request.query,
            suggestions=suggestions,
            request_id=request_id
        )
    
    # Helper Methods
    
    async def _get_mock_places_near_location(
        self,
        location: Location,
        radius_meters: float,
        categories: Optional[List[CategoryType]] = None,
        keywords: Optional[str] = None,
        min_rating: Optional[float] = None,
        price_levels: Optional[List[PriceLevel]] = None,
        open_now: Optional[bool] = None,
        limit: int = 50
    ) -> List[Place]:
        """Generate mock places for demonstration."""
        places = []
        
        # Mock data generation
        place_templates = [
            {"name": "Local Coffee Shop", "category": CategoryType.RESTAURANT, "rating": 4.2},
            {"name": "Downtown Hotel", "category": CategoryType.HOTEL, "rating": 4.0},
            {"name": "Shopping Center", "category": CategoryType.SHOPPING, "rating": 3.8},
            {"name": "City Theater", "category": CategoryType.ENTERTAINMENT, "rating": 4.5},
            {"name": "History Museum", "category": CategoryType.TOURISM, "rating": 4.3},
            {"name": "Medical Center", "category": CategoryType.HEALTHCARE, "rating": 4.1},
            {"name": "University Campus", "category": CategoryType.EDUCATION, "rating": 4.4},
            {"name": "Train Station", "category": CategoryType.TRANSPORTATION, "rating": 3.5},
            {"name": "City Park", "category": CategoryType.RECREATION, "rating": 4.6},
            {"name": "Business District", "category": CategoryType.BUSINESS, "rating": 3.9}
        ]
        
        for i, template in enumerate(place_templates[:limit]):
            # Apply category filter
            if categories and template["category"] not in categories:
                continue
            
            # Apply rating filter
            if min_rating and template["rating"] < min_rating:
                continue
            
            # Generate location within radius
            bearing = (i * 36) % 360  # Distribute around circle
            distance = radius_meters * 0.8 * (i / len(place_templates))
            place_location = self._offset_location(location, bearing, distance)
            
            place = Place(
                id=f"place_{i}_{location.latitude}_{location.longitude}",
                name=f"{template['name']} #{i+1}",
                location=place_location,
                address=f"{100 + i} Main Street",
                category=template["category"],
                rating=template["rating"],
                review_count=50 + i * 10,
                popularity_score=min(1.0, template["rating"] / 5.0 + 0.1),
                price_level=PriceLevel.MODERATE,
                amenities=["wifi", "parking"],
                tags=["popular", "local"],
                verified=True,
                created_at=datetime.utcnow() - timedelta(days=30),
                updated_at=datetime.utcnow(),
                distance_meters=distance
            )
            places.append(place)
        
        return places
    
    async def _calculate_recommendation_score(
        self,
        place: Place,
        query_location: Location,
        user_id: Optional[str],
        request: Optional[Any]
    ) -> RecommendationScore:
        """Calculate recommendation score for a place."""
        # Distance score (closer is better)
        if place.distance_meters is not None:
            max_distance = 10000  # 10km normalization
            distance_score = max(0, 1 - (place.distance_meters / max_distance))
        else:
            distance_score = 0.5
        
        # Rating score
        rating_score = (place.rating / 5.0) if place.rating else 0.5
        
        # Popularity score
        popularity_score = place.popularity_score
        
        # Relevance score (placeholder)
        relevance_score = 0.8
        
        # Overall score (weighted combination)
        overall_score = (
            distance_score * 0.3 +
            rating_score * 0.3 +
            popularity_score * 0.2 +
            relevance_score * 0.2
        )
        
        return RecommendationScore(
            overall_score=min(1.0, overall_score),
            distance_score=distance_score,
            rating_score=rating_score,
            popularity_score=popularity_score,
            relevance_score=relevance_score
        )
    
    def _generate_recommendation_reasons(
        self,
        place: Place,
        score: RecommendationScore
    ) -> List[str]:
        """Generate human-readable reasons for recommendation."""
        reasons = []
        
        if score.rating_score > 0.8:
            reasons.append(f"Highly rated ({place.rating:.1f}/5)")
        
        if score.distance_score > 0.8:
            reasons.append("Very close to your location")
        
        if score.popularity_score > 0.8:
            reasons.append("Popular among locals")
        
        if place.verified:
            reasons.append("Verified business")
        
        if not reasons:
            reasons.append("Good match for your search")
        
        return reasons
    
    def _sort_recommendations(
        self,
        recommendations: List[PlaceRecommendation],
        sort_by: SortBy
    ) -> List[PlaceRecommendation]:
        """Sort recommendations based on the specified criteria."""
        if sort_by == SortBy.DISTANCE:
            return sorted(recommendations, key=lambda x: x.place.distance_meters or 0)
        elif sort_by == SortBy.RATING:
            return sorted(recommendations, key=lambda x: x.place.rating or 0, reverse=True)
        elif sort_by == SortBy.POPULARITY:
            return sorted(recommendations, key=lambda x: x.place.popularity_score, reverse=True)
        elif sort_by == SortBy.RELEVANCE:
            return sorted(recommendations, key=lambda x: x.score.overall_score, reverse=True)
        else:
            return recommendations
    
    async def _get_user_preferences(self, user_id: str) -> UserPreferences:
        """Get user preferences (mock implementation)."""
        # In production, this would query user preferences from database
        return UserPreferences(
            user_id=user_id,
            preferred_categories=[CategoryType.RESTAURANT, CategoryType.ENTERTAINMENT],
            preferred_price_levels=[PriceLevel.MODERATE],
            rating_threshold=4.0,
            max_travel_distance=5000
        )
    
    async def _enhance_score_with_personalization(
        self,
        base_score: RecommendationScore,
        place: Place,
        user_prefs: UserPreferences,
        request: PersonalizedRecommendationRequest
    ) -> RecommendationScore:
        """Enhance recommendation score with personalization."""
        personalization_boost = 0
        
        # Category preference boost
        if place.category in user_prefs.preferred_categories:
            personalization_boost += 0.2
        
        # Price level preference
        if place.price_level in user_prefs.preferred_price_levels:
            personalization_boost += 0.1
        
        # Rating threshold
        if place.rating and place.rating >= user_prefs.rating_threshold:
            personalization_boost += 0.1
        
        # Apply boost
        enhanced_score = base_score.overall_score + personalization_boost
        base_score.overall_score = min(1.0, enhanced_score)
        base_score.personalization_score = personalization_boost
        
        return base_score
    
    def _generate_personalization_reasons(
        self,
        place: Place,
        user_prefs: UserPreferences
    ) -> List[str]:
        """Generate personalization-based reasons."""
        reasons = []
        
        if place.category in user_prefs.preferred_categories:
            reasons.append(f"Matches your interest in {place.category.value}")
        
        if place.price_level in user_prefs.preferred_price_levels:
            reasons.append("Fits your price preferences")
        
        return reasons
    
    def _apply_diversity_filtering(
        self,
        recommendations: List[PlaceRecommendation],
        diversity_factor: float
    ) -> List[PlaceRecommendation]:
        """Apply diversity filtering to recommendations."""
        if not recommendations or diversity_factor == 0:
            return recommendations
        
        diverse_recs = []
        used_categories = set()
        
        # Sort by score first
        sorted_recs = sorted(recommendations, key=lambda x: x.score.overall_score, reverse=True)
        
        # Apply diversity
        for rec in sorted_recs:
            category_penalty = len([c for c in used_categories if c == rec.place.category]) * diversity_factor
            adjusted_score = rec.score.overall_score - category_penalty
            
            if adjusted_score > 0.3:  # Minimum threshold
                diverse_recs.append(rec)
                used_categories.add(rec.place.category)
        
        return diverse_recs
    
    def _calculate_trending_boost(self, place: Place, time_period_days: int) -> float:
        """Calculate trending boost for a place."""
        # Mock trending calculation
        base_trend = place.popularity_score * 0.3
        recency_factor = max(0, 1 - (time_period_days / 365))
        return base_trend * recency_factor
    
    def _analyze_category_trends(
        self,
        trending_places: List[PlaceRecommendation]
    ) -> Dict[str, float]:
        """Analyze trending categories."""
        category_counts = Counter([p.place.category for p in trending_places])
        total = len(trending_places)
        
        return {
            category.value: count / total 
            for category, count in category_counts.items()
        } if total > 0 else {}
    
    async def _get_place_by_id(self, place_id: str) -> Optional[Place]:
        """Get a place by ID (mock implementation)."""
        # Mock place retrieval
        return Place(
            id=place_id,
            name="Reference Place",
            location=Location(latitude=40.7128, longitude=-74.0060),
            category=CategoryType.RESTAURANT,
            rating=4.2,
            review_count=150,
            popularity_score=0.8,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    
    def _calculate_place_similarity(self, place1: Place, place2: Place) -> float:
        """Calculate similarity between two places."""
        similarity = 0
        
        # Category match
        if place1.category == place2.category:
            similarity += 0.4
        
        # Price level similarity
        if place1.price_level == place2.price_level:
            similarity += 0.2
        
        # Rating similarity
        if place1.rating and place2.rating:
            rating_diff = abs(place1.rating - place2.rating)
            rating_similarity = max(0, 1 - (rating_diff / 5))
            similarity += rating_similarity * 0.2
        
        # Amenity overlap
        amenity_overlap = len(set(place1.amenities) & set(place2.amenities))
        if place1.amenities or place2.amenities:
            max_amenities = max(len(place1.amenities), len(place2.amenities))
            similarity += (amenity_overlap / max_amenities) * 0.2 if max_amenities > 0 else 0
        
        return min(1.0, similarity)
    
    def _calculate_route_detour(
        self,
        start: Location,
        end: Location,
        place: Location
    ) -> float:
        """Calculate detour distance for visiting a place on a route."""
        # Simple implementation - distance to place + distance from place to end - direct distance
        direct_distance = self._haversine_distance(
            start.latitude, start.longitude,
            end.latitude, end.longitude
        )
        
        detour_distance = (
            self._haversine_distance(
                start.latitude, start.longitude,
                place.latitude, place.longitude
            ) +
            self._haversine_distance(
                place.latitude, place.longitude,
                end.latitude, end.longitude
            ) - direct_distance
        )
        
        return max(0, detour_distance)
    
    def _calculate_text_similarity(self, query: str, text: str) -> float:
        """Calculate text similarity for autocomplete."""
        query = query.lower().strip()
        text = text.lower().strip()
        
        if query in text:
            return 1.0 if query == text else 0.8
        
        # Simple word overlap calculation
        query_words = set(query.split())
        text_words = set(text.split())
        
        if not query_words:
            return 0
        
        overlap = len(query_words & text_words)
        return overlap / len(query_words)
    
    def _offset_location(
        self,
        location: Location,
        bearing_degrees: float,
        distance_meters: float
    ) -> Location:
        """Offset a location by bearing and distance."""
        R = 6371000  # Earth radius in meters
        
        lat1 = math.radians(location.latitude)
        lon1 = math.radians(location.longitude)
        bearing = math.radians(bearing_degrees)
        
        lat2 = math.asin(
            math.sin(lat1) * math.cos(distance_meters / R) +
            math.cos(lat1) * math.sin(distance_meters / R) * math.cos(bearing)
        )
        
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(distance_meters / R) * math.cos(lat1),
            math.cos(distance_meters / R) - math.sin(lat1) * math.sin(lat2)
        )
        
        return Location(
            latitude=math.degrees(lat2),
            longitude=math.degrees(lon2)
        )
    
    def _haversine_distance(
        self,
        lat1: float, lon1: float,
        lat2: float, lon2: float
    ) -> float:
        """Calculate haversine distance between two points."""
        R = 6371000  # Earth radius in meters
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def _generate_search_cache_key(
        self,
        request: NearbySearchRequest,
        user_id: Optional[str]
    ) -> str:
        """Generate cache key for search request."""
        key_parts = [
            f"lat_{request.location.latitude:.6f}",
            f"lon_{request.location.longitude:.6f}",
            f"radius_{request.radius_meters}",
            f"categories_{sorted(request.categories) if request.categories else 'all'}",
            f"sort_{request.sort_by}",
            f"user_{user_id or 'anonymous'}"
        ]
        return "_".join(key_parts)
    
    async def _get_cached_recommendations(
        self,
        cache_key: str
    ) -> Optional[NearbySearchResponse]:
        """Get cached recommendations."""
        try:
            cached_data = await redis_client.get(f"recommendations:{cache_key}")
            if cached_data:
                return NearbySearchResponse.model_validate_json(cached_data)
        except Exception:
            pass
        return None
    
    async def _cache_recommendations(
        self,
        cache_key: str,
        response: NearbySearchResponse
    ):
        """Cache recommendations."""
        try:
            await redis_client.setex(
                f"recommendations:{cache_key}",
                self.cache_ttl,
                response.model_dump_json()
            )
        except Exception:
            pass


# Singleton instance
recommendation_service = RecommendationService()