from sqlalchemy import text
from app.db import engine
DDL="""
CREATE TABLE IF NOT EXISTS plugins (plugin_id TEXT PRIMARY KEY,name TEXT NOT NULL,version TEXT NOT NULL,plugin_type TEXT NOT NULL,protocol TEXT,capabilities JSONB NOT NULL DEFAULT '[]',configuration_schema JSONB NOT NULL DEFAULT '{}',configuration JSONB NOT NULL DEFAULT '{}',enabled BOOLEAN NOT NULL DEFAULT TRUE,status TEXT NOT NULL DEFAULT 'REGISTERED',status_message TEXT,metrics JSONB NOT NULL DEFAULT '{}',last_heartbeat TIMESTAMPTZ,registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS plugin_logs (log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),plugin_id TEXT NOT NULL,level TEXT NOT NULL,message TEXT NOT NULL,details JSONB NOT NULL DEFAULT '{}',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS artifacts (artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),name TEXT NOT NULL,artifact_type TEXT NOT NULL,content_type TEXT NOT NULL,object_name TEXT NOT NULL UNIQUE,size_bytes BIGINT NOT NULL,sha256 TEXT NOT NULL,related_entity_ids JSONB NOT NULL DEFAULT '[]',related_task_ids JSONB NOT NULL DEFAULT '[]',related_plugin_id TEXT,metadata JSONB NOT NULL DEFAULT '{}',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
"""
async def ensure_schema():
    async with engine.begin() as conn:
        for statement in [x.strip() for x in DDL.split(';') if x.strip()]: await conn.execute(text(statement))
