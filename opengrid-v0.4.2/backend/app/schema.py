from sqlalchemy import text
from app.db import engine
DDL="""
CREATE TABLE IF NOT EXISTS plugins (plugin_id TEXT PRIMARY KEY,name TEXT NOT NULL,version TEXT NOT NULL,plugin_type TEXT NOT NULL,protocol TEXT,capabilities JSONB NOT NULL DEFAULT '[]',configuration_schema JSONB NOT NULL DEFAULT '{}',configuration JSONB NOT NULL DEFAULT '{}',enabled BOOLEAN NOT NULL DEFAULT TRUE,status TEXT NOT NULL DEFAULT 'REGISTERED',status_message TEXT,metrics JSONB NOT NULL DEFAULT '{}',last_heartbeat TIMESTAMPTZ,registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS plugin_logs (log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),plugin_id TEXT NOT NULL,level TEXT NOT NULL,message TEXT NOT NULL,details JSONB NOT NULL DEFAULT '{}',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS artifacts (artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),name TEXT NOT NULL,artifact_type TEXT NOT NULL,content_type TEXT NOT NULL,object_name TEXT NOT NULL UNIQUE,size_bytes BIGINT NOT NULL,sha256 TEXT NOT NULL,related_entity_ids JSONB NOT NULL DEFAULT '[]',related_task_ids JSONB NOT NULL DEFAULT '[]',related_plugin_id TEXT,metadata JSONB NOT NULL DEFAULT '{}',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS entity_location_samples (
    sample_id BIGSERIAL PRIMARY KEY,
    entity_id TEXT NOT NULL,
    revision BIGINT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    heading_degrees DOUBLE PRECISION,
    speed_mps DOUBLE PRECISION,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(entity_id, revision)
);
CREATE INDEX IF NOT EXISTS entity_location_samples_entity_time_idx
    ON entity_location_samples(entity_id, observed_at);
"""
async def ensure_schema():
    async with engine.begin() as conn:
        for statement in [x.strip() for x in DDL.split(';') if x.strip()]: await conn.execute(text(statement))


async def seed_installed_plugins() -> None:
    """Installed plugin manifests should be visible even before first heartbeat."""
    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO plugins (
                plugin_id, name, version, plugin_type, protocol, capabilities,
                configuration_schema, configuration, enabled, status,
                status_message, metrics
            )
            VALUES (
                'opengrid.ais.reference',
                'Reference AIS',
                '0.1.0',
                'DATA_SOURCE',
                'AIS',
                '["entity.publish","entity.patch","artifact.publish"]'::jsonb,
                '{"type":"object","properties":{"input_mode":{"type":"string","enum":["replay","udp","tcp"]}}}'::jsonb,
                '{"input_mode":"replay"}'::jsonb,
                TRUE,
                'OFFLINE',
                'Awaiting plugin heartbeat',
                '{}'::jsonb
            )
            ON CONFLICT (plugin_id) DO NOTHING
        """))

async def backfill_location_samples() -> None:
    """Populate the durable location projection from existing revisions."""
    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO entity_location_samples (
                entity_id, revision, latitude, longitude,
                heading_degrees, speed_mps, observed_at
            )
            SELECT
                entity_id,
                revision,
                CASE
                    WHEN component_name = 'location'
                    THEN (payload->>'latitude')::double precision
                    ELSE (payload->'location'->>'latitude')::double precision
                END,
                CASE
                    WHEN component_name = 'location'
                    THEN (payload->>'longitude')::double precision
                    ELSE (payload->'location'->>'longitude')::double precision
                END,
                CASE
                    WHEN component_name = 'location'
                    THEN NULLIF(payload->>'heading_degrees','')::double precision
                    ELSE NULLIF(payload->'location'->>'heading_degrees','')::double precision
                END,
                CASE
                    WHEN component_name = 'location'
                    THEN NULLIF(payload->>'speed_mps','')::double precision
                    ELSE NULLIF(payload->'location'->>'speed_mps','')::double precision
                END,
                received_time
            FROM entity_revisions
            WHERE (
                component_name = 'location'
                AND payload ? 'latitude'
                AND payload ? 'longitude'
            ) OR (
                component_name IS NULL
                AND payload ? 'location'
                AND payload->'location' ? 'latitude'
                AND payload->'location' ? 'longitude'
            )
            ON CONFLICT (entity_id, revision) DO NOTHING
        """))
