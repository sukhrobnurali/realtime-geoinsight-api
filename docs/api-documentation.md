# GeoInsight API Documentation

## Overview

GeoInsight is a production-ready geospatial analytics API that provides real-time location intelligence, device tracking, geofencing, route optimization, and location-based recommendations. Built with FastAPI, PostgreSQL with PostGIS, and Redis for high-performance spatial operations.

## Base URL

```
https://api.geoinsight.example.com/api/v1
```

## Authentication

The API uses API key authentication. Include your API key in the request headers:

```http
X-API-Key: your-api-key-here
```

For authenticated endpoints, you also need a Bearer token:

```http
Authorization: Bearer your-jwt-token
```

## Rate Limiting

API requests are rate-limited based on your subscription tier:

| Tier | Requests/Minute | Requests/Hour | Requests/Day |
|------|----------------|---------------|--------------|
| Free | 60 | 1,000 | 10,000 |
| Basic | 300 | 10,000 | 100,000 |
| Professional | 1,000 | 50,000 | 1,000,000 |
| Enterprise | 5,000 | 200,000 | 5,000,000 |

Rate limit headers are included in responses:
- `X-RateLimit-Limit`: Request limit for current window
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Timestamp when rate limit resets

## Error Handling

The API uses standard HTTP status codes and returns errors in a consistent format:

```json
{
  "error": "Error message",
  "detail": "Detailed error description",
  "timestamp": "2025-07-16T12:00:00Z",
  "request_id": "req_123456"
}
```

### Common Status Codes

- `200 OK`: Request successful
- `201 Created`: Resource created successfully
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `422 Unprocessable Entity`: Validation error
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error

## Endpoints

### Authentication

#### POST /auth/register

Register a new user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "username": "username",
  "password": "secure_password",
  "full_name": "John Doe"
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "username": "username",
  "full_name": "John Doe",
  "is_active": true,
  "created_at": "2025-07-16T12:00:00Z"
}
```

#### POST /auth/login

Authenticate and receive access token.

**Request Body:**
```json
{
  "username": "username",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "username",
    "email": "user@example.com"
  }
}
```

### Device Management

#### POST /devices

Create a new device for tracking.

**Request Body:**
```json
{
  "device_name": "John's iPhone",
  "device_type": "smartphone",
  "metadata": {
    "manufacturer": "Apple",
    "model": "iPhone 13",
    "os_version": "iOS 15.0"
  }
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "device_name": "John's iPhone",
  "device_type": "smartphone",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "is_active": true,
  "created_at": "2025-07-16T12:00:00Z",
  "last_latitude": null,
  "last_longitude": null,
  "last_seen": null,
  "metadata": {
    "manufacturer": "Apple",
    "model": "iPhone 13",
    "os_version": "iOS 15.0"
  }
}
```

#### GET /devices

Get list of user's devices.

**Query Parameters:**
- `skip` (optional): Number of records to skip (default: 0)
- `limit` (optional): Maximum number of records to return (default: 100)
- `device_type` (optional): Filter by device type
- `is_active` (optional): Filter by active status

**Response:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "device_name": "John's iPhone",
    "device_type": "smartphone",
    "is_active": true,
    "last_latitude": 52.520008,
    "last_longitude": 13.404954,
    "last_seen": "2025-07-16T11:30:00Z"
  }
]
```

#### GET /devices/{device_id}

Get specific device details.

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "device_name": "John's iPhone",
  "device_type": "smartphone",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "is_active": true,
  "created_at": "2025-07-16T12:00:00Z",
  "last_latitude": 52.520008,
  "last_longitude": 13.404954,
  "last_seen": "2025-07-16T11:30:00Z",
  "metadata": {}
}
```

#### PUT /devices/{device_id}/location

Update device location.

**Request Body:**
```json
{
  "latitude": 52.520008,
  "longitude": 13.404954,
  "timestamp": "2025-07-16T12:00:00Z",
  "accuracy": 5.0,
  "speed": 15.5,
  "heading": 180.0
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "device_name": "John's iPhone",
  "last_latitude": 52.520008,
  "last_longitude": 13.404954,
  "last_seen": "2025-07-16T12:00:00Z",
  "location_updated": true
}
```

#### GET /devices/nearby

Find devices within a radius.

**Query Parameters:**
- `latitude` (required): Center latitude
- `longitude` (required): Center longitude  
- `radius_meters` (required): Search radius in meters

**Response:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "device_name": "John's iPhone",
    "distance_meters": 150.5,
    "last_latitude": 52.520008,
    "last_longitude": 13.404954,
    "last_seen": "2025-07-16T11:30:00Z"
  }
]
```

#### GET /devices/{device_id}/trajectory

Get device movement trajectory.

**Query Parameters:**
- `hours` (optional): Time period in hours (default: 24)

**Response:**
```json
{
  "device_id": "550e8400-e29b-41d4-a716-446655440001",
  "time_period_hours": 24,
  "trajectory_points": [
    {
      "latitude": 52.520008,
      "longitude": 13.404954,
      "timestamp": "2025-07-16T11:30:00Z",
      "accuracy": 5.0,
      "speed": 15.5
    }
  ],
  "total_distance_meters": 1250.0,
  "average_speed_kmh": 25.5
}
```

### Geofence Management

#### POST /geofences

Create a new geofence.

**Request Body (Polygon):**
```json
{
  "name": "Office Area",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[
      [13.3, 52.5],
      [13.3, 52.55],
      [13.45, 52.55],
      [13.45, 52.5],
      [13.3, 52.5]
    ]]
  },
  "trigger_type": "enter",
  "metadata": {
    "description": "Main office building area"
  }
}
```

**Request Body (Circular):**
```json
{
  "name": "Store Location",
  "geometry": {
    "type": "Point",
    "coordinates": [13.404954, 52.520008]
  },
  "radius": 500,
  "trigger_type": "both",
  "metadata": {
    "store_id": "store_123"
  }
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "name": "Office Area",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "geometry": "POLYGON((13.3 52.5, 13.3 52.55, 13.45 52.55, 13.45 52.5, 13.3 52.5))",
  "trigger_type": "enter",
  "is_active": true,
  "created_at": "2025-07-16T12:00:00Z",
  "metadata": {
    "description": "Main office building area"
  }
}
```

#### GET /geofences

Get list of user's geofences.

**Query Parameters:**
- `skip` (optional): Number of records to skip
- `limit` (optional): Maximum number of records to return
- `is_active` (optional): Filter by active status

#### GET /geofences/{geofence_id}

Get specific geofence details.

#### PUT /geofences/{geofence_id}

Update geofence properties.

#### DELETE /geofences/{geofence_id}

Delete a geofence.

#### POST /geofences/check

Check if a point is within any geofences.

**Request Body:**
```json
{
  "latitude": 52.525,
  "longitude": 13.375,
  "device_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

**Response:**
```json
{
  "point": {
    "latitude": 52.525,
    "longitude": 13.375
  },
  "triggered_geofences": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "name": "Office Area",
      "trigger_type": "enter",
      "event_type": "enter"
    }
  ]
}
```

### Route Optimization

#### POST /routes/optimize

Optimize route for multiple waypoints.

**Request Body:**
```json
{
  "start_location": {
    "latitude": 52.520008,
    "longitude": 13.404954
  },
  "end_location": {
    "latitude": 52.500342,
    "longitude": 13.425293
  },
  "waypoints": [
    {
      "latitude": 52.516275,
      "longitude": 13.377704
    }
  ],
  "optimization_type": "shortest_time",
  "constraints": {
    "max_distance_km": 50,
    "vehicle_type": "car"
  }
}
```

**Response:**
```json
{
  "optimized_route": [
    {
      "latitude": 52.520008,
      "longitude": 13.404954,
      "order": 0
    },
    {
      "latitude": 52.516275,
      "longitude": 13.377704,
      "order": 1
    },
    {
      "latitude": 52.500342,
      "longitude": 13.425293,
      "order": 2
    }
  ],
  "total_distance_km": 8.5,
  "total_duration_minutes": 25,
  "optimization_savings": {
    "distance_saved_km": 2.1,
    "time_saved_minutes": 8
  }
}
```

#### POST /routes/directions

Get turn-by-turn directions between points.

**Request Body:**
```json
{
  "start_location": {
    "latitude": 52.520008,
    "longitude": 13.404954
  },
  "end_location": {
    "latitude": 52.500342,
    "longitude": 13.425293
  },
  "route_type": "fastest"
}
```

### Location-Based Recommendations

#### POST /recommendations/nearby

Get nearby points of interest.

**Request Body:**
```json
{
  "latitude": 52.520008,
  "longitude": 13.404954,
  "radius_km": 2,
  "categories": ["restaurant", "hotel"],
  "limit": 20
}
```

**Response:**
```json
{
  "location": {
    "latitude": 52.520008,
    "longitude": 13.404954
  },
  "radius_km": 2,
  "recommendations": [
    {
      "id": "poi_123",
      "name": "Restaurant Berlin",
      "category": "restaurant",
      "latitude": 52.521500,
      "longitude": 13.406000,
      "distance_meters": 250.5,
      "rating": 4.5,
      "description": "Fine dining restaurant",
      "metadata": {
        "cuisine": "German",
        "price_range": "€€€"
      }
    }
  ],
  "total_results": 15
}
```

#### POST /recommendations/personalized

Get personalized recommendations based on user preferences.

**Request Body:**
```json
{
  "latitude": 52.520008,
  "longitude": 13.404954,
  "user_preferences": {
    "categories": ["restaurant", "shopping"],
    "price_range": "€€",
    "rating_threshold": 4.0
  },
  "context": {
    "time_of_day": "evening",
    "purpose": "leisure"
  }
}
```

### Monitoring and Analytics

#### GET /monitoring/health

Get comprehensive system health status.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-07-16T12:00:00Z",
  "version": "1.0.0",
  "components": {
    "database": {
      "status": "healthy",
      "response_time_ms": 25
    },
    "redis": {
      "status": "healthy", 
      "response_time_ms": 5
    },
    "osrm": {
      "status": "healthy",
      "response_time_ms": 150
    }
  },
  "system": {
    "cpu_usage_percent": 45.2,
    "memory_usage_percent": 62.1,
    "disk_usage_percent": 35.8
  }
}
```

#### GET /monitoring/metrics

Get Prometheus metrics (for monitoring systems).

#### GET /monitoring/performance

Get API performance statistics.

**Response:**
```json
{
  "time_period_hours": 1,
  "operations": {
    "device_location_update": {
      "count": 1250,
      "avg_ms": 45.2,
      "p95_ms": 125.0,
      "p99_ms": 250.0
    },
    "geofence_check": {
      "count": 850,
      "avg_ms": 35.1,
      "p95_ms": 95.0,
      "p99_ms": 180.0
    }
  }
}
```

## Data Models

### Device

```json
{
  "id": "uuid",
  "device_name": "string",
  "device_type": "smartphone|tablet|tracker|vehicle|other",
  "user_id": "uuid",
  "is_active": "boolean",
  "created_at": "datetime",
  "updated_at": "datetime",
  "last_latitude": "float|null",
  "last_longitude": "float|null", 
  "last_seen": "datetime|null",
  "metadata": "object"
}
```

### Geofence

```json
{
  "id": "uuid",
  "name": "string",
  "user_id": "uuid", 
  "geometry": "GeoJSON geometry",
  "radius": "float|null",
  "trigger_type": "enter|exit|both",
  "is_active": "boolean",
  "created_at": "datetime",
  "updated_at": "datetime",
  "metadata": "object"
}
```

### Location Point

```json
{
  "latitude": "float (-90 to 90)",
  "longitude": "float (-180 to 180)",
  "timestamp": "datetime (ISO 8601)",
  "accuracy": "float (meters)",
  "speed": "float (m/s)|null",
  "heading": "float (0-360 degrees)|null"
}
```

## SDKs and Integration

### JavaScript/TypeScript

```javascript
import { GeoInsightAPI } from '@geoinsight/sdk';

const client = new GeoInsightAPI({
  apiKey: 'your-api-key',
  baseUrl: 'https://api.geoinsight.example.com/api/v1'
});

// Update device location
await client.devices.updateLocation('device-id', {
  latitude: 52.520008,
  longitude: 13.404954,
  timestamp: new Date().toISOString()
});
```

### Python

```python
from geoinsight import GeoInsightClient

client = GeoInsightClient(
    api_key='your-api-key',
    base_url='https://api.geoinsight.example.com/api/v1'
)

# Create geofence
geofence = client.geofences.create({
    'name': 'Office Area',
    'geometry': {
        'type': 'Polygon',
        'coordinates': [[[13.3, 52.5], [13.3, 52.55], [13.45, 52.55], [13.45, 52.5], [13.3, 52.5]]]
    },
    'trigger_type': 'enter'
})
```

### cURL Examples

```bash
# Create device
curl -X POST "https://api.geoinsight.example.com/api/v1/devices" \
  -H "X-API-Key: your-api-key" \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "device_name": "Test Device",
    "device_type": "smartphone"
  }'

# Update location
curl -X PUT "https://api.geoinsight.example.com/api/v1/devices/{device-id}/location" \
  -H "X-API-Key: your-api-key" \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 52.520008,
    "longitude": 13.404954,
    "timestamp": "2025-07-16T12:00:00Z"
  }'
```

## Webhooks

Configure webhooks to receive real-time notifications for geofence events, device status changes, and other important events.

### Webhook Configuration

```json
{
  "url": "https://your-app.com/webhooks/geoinsight",
  "events": ["geofence.enter", "geofence.exit", "device.offline"],
  "secret": "webhook-secret-key"
}
```

### Webhook Payload Example

```json
{
  "event_type": "geofence.enter",
  "timestamp": "2025-07-16T12:00:00Z",
  "data": {
    "device_id": "550e8400-e29b-41d4-a716-446655440001",
    "geofence_id": "550e8400-e29b-41d4-a716-446655440002",
    "location": {
      "latitude": 52.525,
      "longitude": 13.375
    }
  }
}
```

## Best Practices

### Location Updates
- Batch location updates when possible using `/devices/batch-location-update`
- Include timestamp in location data for accurate trajectory analysis
- Set appropriate accuracy values for filtering unreliable GPS data

### Geofence Design
- Use simple polygon shapes for better performance
- Avoid overlapping geofences when possible
- Set reasonable buffer zones around critical areas

### Rate Limiting
- Implement exponential backoff for rate-limited requests
- Cache responses when appropriate to reduce API calls
- Use webhooks instead of polling for real-time updates

### Error Handling
- Always check HTTP status codes
- Implement retry logic for temporary failures (5xx errors)
- Log request IDs for debugging support requests

## Support

- Documentation: https://docs.geoinsight.example.com
- API Status: https://status.geoinsight.example.com  
- Support Email: support@geoinsight.example.com
- Developer Forum: https://community.geoinsight.example.com