from celery import Celery
from app.config import settings

# Create Celery instance
celery_app = Celery(
    "geoinsight",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.services.tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Task routing
celery_app.conf.task_routes = {
    "app.services.tasks.process_geofence_check": {"queue": "geofence"},
    "app.services.tasks.generate_heatmap": {"queue": "analytics"},
    "app.services.tasks.optimize_route": {"queue": "routing"},
}

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "cleanup-expired-sessions": {
        "task": "app.services.tasks.cleanup_expired_sessions",
        "schedule": 3600.0,  # Run every hour
    },
}

if __name__ == "__main__":
    celery_app.start()