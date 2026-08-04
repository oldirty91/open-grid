CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS entities_current (
    entity_id TEXT PRIMARY KEY,
    revision BIGINT NOT NULL DEFAULT 1,
    is_live BOOLEAN NOT NULL DEFAULT TRUE,
    template TEXT NOT NULL DEFAULT 'UNKNOWN',
    expiry_time TIMESTAMPTZ,
    components JSONB NOT NULL DEFAULT '{}',
    component_provenance JSONB NOT NULL DEFAULT '{}',
    geom GEOMETRY(Point, 4326),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS entities_current_geom_gix ON entities_current USING GIST (geom);
CREATE INDEX IF NOT EXISTS entities_current_template_idx ON entities_current(template);
CREATE INDEX IF NOT EXISTS entities_current_components_gin ON entities_current USING GIN(components);

CREATE TABLE IF NOT EXISTS entity_revisions (
    revision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id TEXT NOT NULL,
    revision BIGINT NOT NULL,
    operation TEXT NOT NULL,
    component_name TEXT,
    payload JSONB NOT NULL,
    provenance JSONB NOT NULL DEFAULT '{}',
    source_time TIMESTAMPTZ,
    received_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(entity_id, revision)
);

CREATE INDEX IF NOT EXISTS entity_revisions_entity_idx
    ON entity_revisions(entity_id, revision DESC);
CREATE INDEX IF NOT EXISTS entity_revisions_component_idx
    ON entity_revisions(entity_id, component_name, revision DESC);

CREATE TABLE IF NOT EXISTS tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL DEFAULT '',
    specification JSONB NOT NULL,
    assigned_agent_id TEXT NOT NULL,
    queue_position BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'STATUS_SENT',
    progress DOUBLE PRECISION NOT NULL DEFAULT 0,
    status_message TEXT,
    execution JSONB NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 50,
    timeout_seconds INTEGER,
    maximum_attempts INTEGER NOT NULL DEFAULT 1,
    attempt INTEGER NOT NULL DEFAULT 0,
    depends_on JSONB NOT NULL DEFAULT '[]',
    claimed_at TIMESTAMPTZ,
    claimed_by TEXT,
    created_by TEXT,
    last_updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tasks_agent_queue_idx
    ON tasks(assigned_agent_id, queue_position);
CREATE INDEX IF NOT EXISTS tasks_status_idx ON tasks(status);

CREATE TABLE IF NOT EXISTS task_revisions (
    revision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL,
    status TEXT NOT NULL,
    progress DOUBLE PRECISION NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    actor_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fusion_associations (
    association_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fused_entity_id TEXT NOT NULL UNIQUE,
    source_entity_ids JSONB NOT NULL,
    algorithm TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


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
