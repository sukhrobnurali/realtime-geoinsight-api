-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Create database if not exists (already created by environment variable)
-- PostgreSQL will automatically create the database specified in POSTGRES_DB

-- Set timezone
SET timezone = 'UTC';