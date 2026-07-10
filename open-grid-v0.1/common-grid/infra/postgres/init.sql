CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS entities_current (
 entity_id TEXT PRIMARY KEY, revision BIGINT NOT NULL DEFAULT 1,
 is_live BOOLEAN NOT NULL DEFAULT TRUE, template TEXT NOT NULL,
 expiry_time TIMESTAMPTZ, components JSONB NOT NULL,
 geom GEOMETRY(Point,4326), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), source_update_time TIMESTAMPTZ);
CREATE INDEX IF NOT EXISTS entities_geom_gix ON entities_current USING GIST(geom);
CREATE INDEX IF NOT EXISTS entities_template_idx ON entities_current(template);
CREATE INDEX IF NOT EXISTS entities_components_gin ON entities_current USING GIN(components);
CREATE TABLE IF NOT EXISTS entity_events (
 event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), entity_id TEXT NOT NULL,
 revision BIGINT NOT NULL, event_type TEXT NOT NULL,
 changed_components TEXT[] NOT NULL DEFAULT '{}', payload JSONB NOT NULL,
 actor_id TEXT, source_time TIMESTAMPTZ, received_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 correlation_id UUID DEFAULT gen_random_uuid(), UNIQUE(entity_id,revision));
CREATE INDEX IF NOT EXISTS entity_events_idx ON entity_events(entity_id,revision DESC);
CREATE TABLE IF NOT EXISTS tasks (
 task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), task_type TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', assigned_agents JSONB NOT NULL DEFAULT '[]',
 objective_entity_id TEXT, parameters JSONB NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'DRAFT', progress DOUBLE PRECISION NOT NULL DEFAULT 0,
 status_message TEXT, created_by TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS fusion_associations (
 association_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), fused_entity_id TEXT NOT NULL,
 source_entity_ids JSONB NOT NULL, algorithm TEXT NOT NULL, score DOUBLE PRECISION NOT NULL,
 details JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE UNIQUE INDEX IF NOT EXISTS fusion_fused_idx ON fusion_associations(fused_entity_id);
