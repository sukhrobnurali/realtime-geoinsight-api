"""Optimize spatial indexes and add performance enhancements

Revision ID: 002
Revises: 001
Create Date: 2025-07-16 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add optimized spatial indexes with specific configurations
    
    # Advanced spatial indexes for geofences
    op.execute("""
        DROP INDEX IF EXISTS idx_geofences_geometry;
        CREATE INDEX CONCURRENTLY idx_geofences_geometry_optimized 
        ON geofences USING GIST (geometry) 
        WITH (fillfactor = 90);
    """)
    
    # Add spatial index for geofence centroid for faster proximity searches
    op.execute("""
        CREATE INDEX CONCURRENTLY idx_geofences_centroid 
        ON geofences USING GIST (ST_Centroid(geometry)) 
        WITH (fillfactor = 90);
    """)
    
    # Optimize device location indexes
    op.execute("""
        DROP INDEX IF EXISTS idx_devices_last_location;
        CREATE INDEX CONCURRENTLY idx_devices_last_location_optimized 
        ON devices USING GIST (last_location) 
        WITH (fillfactor = 90);
    """)
    
    # Add composite index for user devices with location
    op.execute("""
        CREATE INDEX CONCURRENTLY idx_devices_user_location 
        ON devices USING GIST (user_id, last_location) 
        WHERE last_location IS NOT NULL;
    """)
    
    # Add time-based index for device updates
    op.create_index('idx_devices_last_seen', 'devices', ['last_seen'], unique=False)
    op.create_index('idx_devices_user_updated', 'devices', ['user_id', 'updated_at'], unique=False)
    
    # Optimize trajectory indexes
    op.execute("""
        DROP INDEX IF EXISTS idx_trajectories_path;
        CREATE INDEX CONCURRENTLY idx_trajectories_path_optimized 
        ON trajectories USING GIST (path) 
        WITH (fillfactor = 90);
    """)
    
    # Add time-based trajectory indexes for efficient querying
    op.create_index('idx_trajectories_device_time', 'trajectories', ['device_id', 'start_time', 'end_time'], unique=False)
    op.create_index('idx_trajectories_recorded_at', 'trajectories', ['recorded_at'], unique=False)
    
    # Optimize trajectory points indexes
    op.execute("""
        DROP INDEX IF EXISTS idx_trajectory_points_location;
        CREATE INDEX CONCURRENTLY idx_trajectory_points_location_optimized 
        ON trajectory_points USING GIST (location) 
        WITH (fillfactor = 90);
    """)
    
    # Add composite index for efficient trajectory point queries
    op.create_index('idx_trajectory_points_traj_time', 'trajectory_points', ['trajectory_id', 'timestamp'], unique=False)
    
    # Add covering index for trajectory point analytics
    op.execute("""
        CREATE INDEX CONCURRENTLY idx_trajectory_points_analytics 
        ON trajectory_points (trajectory_id, timestamp) 
        INCLUDE (speed, heading, accuracy);
    """)
    
    # Add partial indexes for active data
    op.execute("""
        CREATE INDEX CONCURRENTLY idx_devices_active_last_24h 
        ON devices (user_id, last_seen) 
        WHERE last_seen > NOW() - INTERVAL '24 hours';
    """)
    
    op.execute("""
        CREATE INDEX CONCURRENTLY idx_trajectories_recent 
        ON trajectories (device_id, start_time) 
        WHERE start_time > NOW() - INTERVAL '7 days';
    """)
    
    # Add user-specific indexes for better query performance
    op.create_index('idx_users_email_active', 'users', ['email'], unique=True, 
                   postgresql_where=sa.text("is_active = true"))
    
    # Add API key index for faster authentication
    op.create_index('idx_users_api_key_active', 'users', ['api_key'], unique=True,
                   postgresql_where=sa.text("api_key IS NOT NULL AND is_active = true"))


def downgrade() -> None:
    # Remove optimized indexes
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_geofences_geometry_optimized;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_geofences_centroid;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_devices_last_location_optimized;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_devices_user_location;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_trajectories_path_optimized;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_trajectory_points_location_optimized;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_trajectory_points_analytics;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_devices_active_last_24h;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_trajectories_recent;")
    
    # Drop regular indexes
    op.drop_index('idx_devices_last_seen', 'devices')
    op.drop_index('idx_devices_user_updated', 'devices')
    op.drop_index('idx_trajectories_device_time', 'trajectories')
    op.drop_index('idx_trajectories_recorded_at', 'trajectories')
    op.drop_index('idx_trajectory_points_traj_time', 'trajectory_points')
    op.drop_index('idx_users_email_active', 'users')
    op.drop_index('idx_users_api_key_active', 'users')
    
    # Recreate original basic indexes
    op.execute("CREATE INDEX idx_geofences_geometry ON geofences USING GIST(geometry);")
    op.execute("CREATE INDEX idx_devices_last_location ON devices USING GIST(last_location);")
    op.execute("CREATE INDEX idx_trajectories_path ON trajectories USING GIST(path);")
    op.execute("CREATE INDEX idx_trajectory_points_location ON trajectory_points USING GIST(location);")