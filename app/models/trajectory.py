from sqlalchemy import Column, DateTime, ForeignKey, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from geoalchemy2 import Geography
from app.database import Base
import uuid


class Trajectory(Base):
    __tablename__ = "trajectories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    path = Column(Geography("LINESTRING", srid=4326))
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    total_distance = Column(Float)  # in meters
    avg_speed = Column(Float)  # in m/s
    max_speed = Column(Float)  # in m/s
    point_count = Column(Integer, default=0)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    device = relationship("Device", back_populates="trajectories")

    def __repr__(self):
        return f"<Trajectory(id={self.id}, device_id={self.device_id})>"


class TrajectoryPoint(Base):
    __tablename__ = "trajectory_points"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    trajectory_id = Column(UUID(as_uuid=True), ForeignKey("trajectories.id", ondelete="CASCADE"), nullable=False)
    location = Column(Geography("POINT", srid=4326), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    speed = Column(Float)  # in m/s
    heading = Column(Float)  # in degrees
    accuracy = Column(Float)  # in meters
    altitude = Column(Float)  # in meters

    # Relationship
    trajectory = relationship("Trajectory")

    def __repr__(self):
        return f"<TrajectoryPoint(id={self.id}, trajectory_id={self.trajectory_id})>"