"""Add device and trajectory tables

Revision ID: 001
Revises: 
Create Date: 2025-07-16 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create devices table
    op.create_table('devices',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_name', sa.String(length=255), nullable=False),
        sa.Column('device_identifier', sa.String(length=255), nullable=True),
        sa.Column('last_location', geoalchemy2.types.Geography(geometry_type='POINT', srid=4326), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_devices_device_identifier'), 'devices', ['device_identifier'], unique=True)
    op.create_index(op.f('ix_devices_id'), 'devices', ['id'], unique=False)
    
    # Create spatial index for last_location
    op.execute('CREATE INDEX idx_devices_last_location ON devices USING GIST (last_location)')

    # Create trajectories table
    op.create_table('trajectories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('path', geoalchemy2.types.Geography(geometry_type='LINESTRING', srid=4326), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_distance', sa.Float(), nullable=True),
        sa.Column('avg_speed', sa.Float(), nullable=True),
        sa.Column('max_speed', sa.Float(), nullable=True),
        sa.Column('point_count', sa.Integer(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trajectories_id'), 'trajectories', ['id'], unique=False)
    
    # Create spatial index for path
    op.execute('CREATE INDEX idx_trajectories_path ON trajectories USING GIST (path)')

    # Create trajectory_points table
    op.create_table('trajectory_points',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trajectory_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('location', geoalchemy2.types.Geography(geometry_type='POINT', srid=4326), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('speed', sa.Float(), nullable=True),
        sa.Column('heading', sa.Float(), nullable=True),
        sa.Column('accuracy', sa.Float(), nullable=True),
        sa.Column('altitude', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['trajectory_id'], ['trajectories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trajectory_points_id'), 'trajectory_points', ['id'], unique=False)
    
    # Create spatial index for location
    op.execute('CREATE INDEX idx_trajectory_points_location ON trajectory_points USING GIST (location)')
    # Create time-based index for efficient querying
    op.create_index('ix_trajectory_points_timestamp', 'trajectory_points', ['timestamp'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order due to foreign key constraints
    op.drop_table('trajectory_points')
    op.drop_table('trajectories')
    op.drop_table('devices')