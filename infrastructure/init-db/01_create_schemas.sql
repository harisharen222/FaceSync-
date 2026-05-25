-- init-db/01_create_schemas.sql
-- Runs automatically when the PostgreSQL container first starts.
-- Creates isolated schemas for each microservice (database-per-service pattern).

-- Phase 1: Auth Service
CREATE SCHEMA IF NOT EXISTS auth_schema;

-- Phase 2 (pre-create for convenience, populated later):
CREATE SCHEMA IF NOT EXISTS enrollment_schema;
CREATE SCHEMA IF NOT EXISTS attendance_schema;
CREATE SCHEMA IF NOT EXISTS models_schema;
CREATE SCHEMA IF NOT EXISTS reporting_schema;
CREATE SCHEMA IF NOT EXISTS audit_schema;
CREATE SCHEMA IF NOT EXISTS notification_schema;

-- Grant all privileges on each schema to the nhai user
GRANT ALL PRIVILEGES ON SCHEMA auth_schema TO nhai;
GRANT ALL PRIVILEGES ON SCHEMA enrollment_schema TO nhai;
GRANT ALL PRIVILEGES ON SCHEMA attendance_schema TO nhai;
GRANT ALL PRIVILEGES ON SCHEMA models_schema TO nhai;
GRANT ALL PRIVILEGES ON SCHEMA reporting_schema TO nhai;
GRANT ALL PRIVILEGES ON SCHEMA audit_schema TO nhai;
GRANT ALL PRIVILEGES ON SCHEMA notification_schema TO nhai;

-- Enable UUID generation extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
