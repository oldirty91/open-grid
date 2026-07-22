import json
import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.artifacts import ensure_bucket, get_object, put_bytes
from app.schema import backfill_location_samples, ensure_schema, seed_installed_plugins
from app.db import get_db
from app.events import event_bus
from app.fusion import correlate_track
from app.models import (
    ComponentPatch,
    EntityUpsert,
    ArtifactCreateText,
    PluginConfigurationPatch,
    PluginHeartbeat,
    PluginLogCreate,
    PluginRegister,
    TaskCancel,
    TaskClaim,
    TaskCreate,
    TaskStatus,
    TaskStatusUpdate,
)
from app.realtime import hub

TAGS = [
    {"name": "Entities", "description": "Composable operational-world entities and component history."},
    {"name": "Tasks", "description": "Durable task creation, queueing, claim and lifecycle."},
    {"name": "Fusion", "description": "Bare-bones source-track correlation."},
    {"name": "Streams", "description": "Live WebSocket update stream."},
    {"name": "Plugins", "description": "Administrative plugin registry, configuration and health."},
    {"name": "Artifacts", "description": "Persistent products backed by MinIO."},
    {"name": "System", "description": "Health and task definition discovery."},
]

TASK_DEFINITIONS = [
 {"type":"opengrid.tasks.v1.Arm","display_name":"Arm","objective_types":["NONE"],"parameter_schema":{"type":"object","properties":{}}},
 {"type":"opengrid.tasks.v1.Disarm","display_name":"Disarm","objective_types":["NONE"],"parameter_schema":{"type":"object","properties":{}}},
 {"type":"opengrid.tasks.v1.Takeoff","display_name":"Takeoff","objective_types":["NONE"],"parameter_schema":{"type":"object","properties":{"altitude_m":{"type":"number","minimum":2,"default":20}}}},
 {"type":"opengrid.tasks.v1.Navigate","display_name":"Navigate","objective_types":["POINT"],"parameter_schema":{"type":"object","properties":{"speed_mps":{"type":"number","minimum":0,"default":3},"arrival_radius_m":{"type":"number","minimum":1,"default":20},"altitude_m":{"type":"number","minimum":2,"default":30}}}},
 {"type":"opengrid.tasks.v1.LaunchAndNavigate","display_name":"Launch & Navigate","objective_types":["POINT"],"parameter_schema":{"type":"object","properties":{"takeoff_altitude_m":{"type":"number","minimum":2,"default":20},"speed_mps":{"type":"number","minimum":0,"default":3},"arrival_radius_m":{"type":"number","minimum":1,"default":20}}}},
 {"type":"opengrid.tasks.v1.Loiter","display_name":"Loiter","objective_types":["POINT"],"parameter_schema":{"type":"object","properties":{"radius_m":{"type":"number","minimum":5,"default":50},"altitude_m":{"type":"number","minimum":2,"default":30}}}},
 {"type":"opengrid.tasks.v1.ReturnToLaunch","display_name":"Return to Launch","objective_types":["NONE"],"parameter_schema":{"type":"object","properties":{}}},
 {"type":"opengrid.tasks.v1.Land","display_name":"Land","objective_types":["NONE"],"parameter_schema":{"type":"object","properties":{}}},
 {"type":"opengrid.tasks.v1.ExecuteMission","display_name":"Execute Mission","objective_types":["ARTIFACT"],"parameter_schema":{"type":"object","properties":{"auto_arm":{"type":"boolean","default":True}}}},
 {"type":"opengrid.tasks.v1.PauseMission","display_name":"Pause Mission","objective_types":["NONE"],"parameter_schema":{"type":"object","properties":{}}},
 {"type":"opengrid.tasks.v1.ResumeMission","display_name":"Resume Mission","objective_types":["NONE"],"parameter_schema":{"type":"object","properties":{}}},
 {"type":"opengrid.tasks.v1.StopMission","display_name":"Stop Mission","objective_types":["NONE"],"parameter_schema":{"type":"object","properties":{}}}
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema()
    await seed_installed_plugins()
    await backfill_location_samples()
    # Artifact storage is optional infrastructure. A slow or unavailable MinIO
    # instance must not prevent the world-model API, plugins, or map from starting.
    artifact_storage_ready = False
    for attempt in range(20):
        try:
            await asyncio.to_thread(ensure_bucket)
            artifact_storage_ready = True
            break
        except Exception as exc:
            if attempt == 19:
                print(f"[artifacts] MinIO unavailable at startup; continuing without artifact storage: {exc}")
                break
            await asyncio.sleep(1)
    app.state.artifact_storage_ready = artifact_storage_ready
    await event_bus.connect()
    yield
    await event_bus.close()

app = FastAPI(
    title="OpenGrid API",
    version="0.10.1",
    description=(
        "OpenGrid is an operational world model built around three core concepts: "
        "Entities, Tasks and Artifacts. v0.2 implements Entities, task queues, "
        "basic fusion and live updates. Artifact storage is scheduled for v0.3."
    ),
    openapi_tags=TAGS,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def template_of(components: dict) -> str:
    return str((components.get("ontology") or {}).get("template") or "UNKNOWN").upper()

def point_of(components: dict):
    location = components.get("location") or {}
    if location.get("latitude") is None or location.get("longitude") is None:
        return None
    return float(location["latitude"]), float(location["longitude"])


async def store_location_sample(
    db: AsyncSession,
    entity_id: str,
    revision: int,
    components: dict,
) -> None:
    location = components.get("location") or {}
    if location.get("latitude") is None or location.get("longitude") is None:
        return
    await db.execute(text("""
        INSERT INTO entity_location_samples (
          entity_id, revision, latitude, longitude,
          heading_degrees, speed_mps, observed_at
        )
        VALUES (
          :entity_id, :revision, :latitude, :longitude,
          :heading, :speed, NOW()
        )
        ON CONFLICT (entity_id, revision) DO NOTHING
    """), {
        "entity_id": entity_id,
        "revision": revision,
        "latitude": float(location["latitude"]),
        "longitude": float(location["longitude"]),
        "heading": location.get("heading_degrees"),
        "speed": location.get("speed_mps"),
    })

async def emit(kind: str, data: dict):
    await event_bus.publish(kind.replace(":", "."), data)
    await hub.broadcast({"type": kind, "data": data})

@app.get("/health", tags=["System"], summary="Service health")
async def health():
    return {"status": "ok", "service": "opengrid-api", "version": "0.10.1", "artifact_storage_ready": bool(getattr(app.state, "artifact_storage_ready", False))}

@app.get("/api/v1/task-definitions", tags=["System"], summary="List task specifications")
async def task_definitions():
    return TASK_DEFINITIONS

@app.put(
    "/api/v1/entities/{entity_id}",
    tags=["Entities"],
    summary="Create or replace an entity",
    description="Creates a new entity or replaces its complete component set while preserving revision history.",
)
async def upsert_entity(entity_id: str, body: EntityUpsert, db: AsyncSession = Depends(get_db)):
    if entity_id != body.entity_id:
        raise HTTPException(400, "Path entity_id must match body entity_id")

    template = template_of(body.components)
    point = point_of(body.components)
    provenance_map = {name: body.provenance for name in body.components}

    result = await db.execute(text("""
        INSERT INTO entities_current (
          entity_id, revision, is_live, template, expiry_time, components,
          component_provenance, geom
        )
        VALUES (
          :entity_id, 1, :is_live, :template, :expiry_time,
          CAST(:components AS JSONB), CAST(:component_provenance AS JSONB),
          CASE WHEN :has_point
            THEN ST_SetSRID(ST_Point(:lon,:lat),4326)
            ELSE NULL
          END
        )
        ON CONFLICT (entity_id) DO UPDATE SET
          revision = entities_current.revision + 1,
          is_live = EXCLUDED.is_live,
          template = EXCLUDED.template,
          expiry_time = EXCLUDED.expiry_time,
          components = EXCLUDED.components,
          component_provenance = EXCLUDED.component_provenance,
          geom = EXCLUDED.geom,
          updated_at = NOW()
        RETURNING entity_id, revision, is_live, template, expiry_time,
                  components, component_provenance, created_at, updated_at
    """), {
        "entity_id": entity_id,
        "is_live": body.is_live,
        "template": template,
        "expiry_time": body.expiry_time,
        "components": json.dumps(body.components),
        "component_provenance": json.dumps(provenance_map),
        "has_point": point is not None,
        "lat": point[0] if point else 0,
        "lon": point[1] if point else 0,
    })
    entity = dict(result.mappings().one())

    await db.execute(text("""
        INSERT INTO entity_revisions (
          entity_id, revision, operation, payload, provenance
        )
        VALUES (
          :entity_id, :revision, 'ENTITY_REPLACE',
          CAST(:payload AS JSONB), CAST(:provenance AS JSONB)
        )
    """), {
        "entity_id": entity_id,
        "revision": entity["revision"],
        "payload": json.dumps(body.components),
        "provenance": json.dumps(body.provenance),
    })

    await store_location_sample(db, entity_id, entity["revision"], body.components)

    fusion = None
    ontology = body.components.get("ontology") or {}
    if (
        body.is_live
        and template == "TRACK"
        and ontology.get("track_type", "SOURCE") != "FUSED"
    ):
        fusion = await correlate_track(db, entity_id, body.components)

    await db.commit()
    await emit("entity.updated", entity)
    if fusion:
        await emit("entity.updated", fusion["entity"])
        await emit("fusion.updated", {k: v for k, v in fusion.items() if k != "entity"})
    return {"entity": entity, "fusion": fusion}

@app.patch(
    "/api/v1/entities/{entity_id}/components/{component_name}",
    tags=["Entities"],
    summary="Replace one entity component",
    description=(
        "Replaces one named component while preserving all unrelated components. "
        "Unknown component names are accepted and retained."
    ),
)
async def patch_component(
    entity_id: str,
    component_name: str,
    body: ComponentPatch,
    db: AsyncSession = Depends(get_db),
):
    locked = await db.execute(text("""
        SELECT entity_id, revision, components, component_provenance
        FROM entities_current
        WHERE entity_id = :entity_id
        FOR UPDATE
    """), {"entity_id": entity_id})
    current = locked.mappings().first()
    if not current:
        raise HTTPException(404, "Entity not found")

    components = dict(current["components"])
    provenance = dict(current["component_provenance"])
    components[component_name] = body.value
    provenance[component_name] = body.provenance
    template = template_of(components)
    point = point_of(components)
    revision = int(current["revision"]) + 1

    result = await db.execute(text("""
        UPDATE entities_current SET
          revision = :revision,
          template = :template,
          components = CAST(:components AS JSONB),
          component_provenance = CAST(:provenance AS JSONB),
          geom = CASE WHEN :has_point
            THEN ST_SetSRID(ST_Point(:lon,:lat),4326)
            ELSE NULL
          END,
          updated_at = NOW()
        WHERE entity_id = :entity_id
        RETURNING entity_id, revision, is_live, template, expiry_time,
                  components, component_provenance, created_at, updated_at
    """), {
        "entity_id": entity_id,
        "revision": revision,
        "template": template,
        "components": json.dumps(components),
        "provenance": json.dumps(provenance),
        "has_point": point is not None,
        "lat": point[0] if point else 0,
        "lon": point[1] if point else 0,
    })
    entity = dict(result.mappings().one())

    await db.execute(text("""
        INSERT INTO entity_revisions (
          entity_id, revision, operation, component_name,
          payload, provenance, source_time
        )
        VALUES (
          :entity_id, :revision, 'COMPONENT_REPLACE', :component_name,
          CAST(:payload AS JSONB), CAST(:provenance AS JSONB), :source_time
        )
    """), {
        "entity_id": entity_id,
        "revision": revision,
        "component_name": component_name,
        "payload": json.dumps(body.value),
        "provenance": json.dumps(body.provenance),
        "source_time": body.source_time,
    })

    await store_location_sample(db, entity_id, revision, components)

    await db.commit()
    await emit("entity.component.updated", {
        "entity": entity,
        "component_name": component_name,
    })
    return entity

@app.get("/api/v1/entities", tags=["Entities"], summary="List current entities")
async def list_entities(
    template: str | None = None,
    live_only: bool = True,
    limit: int = Query(1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    clauses = ["1=1"]
    params = {"limit": limit}
    if template:
        clauses.append("template = :template")
        params["template"] = template.upper()
    if live_only:
        clauses.append("is_live = TRUE")
    result = await db.execute(text(f"""
        SELECT entity_id, revision, is_live, template, expiry_time,
               components, component_provenance, created_at, updated_at
        FROM entities_current
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC
        LIMIT :limit
    """), params)
    return [dict(row) for row in result.mappings()]

@app.get("/api/v1/entities/{entity_id}", tags=["Entities"], summary="Read one entity")
async def get_entity(entity_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT entity_id, revision, is_live, template, expiry_time,
               components, component_provenance, created_at, updated_at
        FROM entities_current
        WHERE entity_id = :entity_id
    """), {"entity_id": entity_id})
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Entity not found")
    return dict(row)

@app.get("/api/v1/entities/{entity_id}/profile", tags=["Entities"], summary="Read entity operational profile")
async def entity_profile(entity_id: str, db: AsyncSession = Depends(get_db)):
    entity_result = await db.execute(text("""SELECT entity_id, revision, is_live, template, expiry_time, components, component_provenance, created_at, updated_at FROM entities_current WHERE entity_id=:entity_id"""), {"entity_id":entity_id})
    entity=entity_result.mappings().first()
    if not entity: raise HTTPException(404,"Entity not found")
    tasks_result=await db.execute(text("""SELECT * FROM tasks WHERE assigned_agent_id=:entity_id OR specification->'objective'->>'entity_id'=:entity_id ORDER BY created_at DESC LIMIT 25"""), {"entity_id":entity_id})
    artifacts_result=await db.execute(text("""SELECT artifact_id,name,artifact_type,content_type,size_bytes,metadata,created_at FROM artifacts WHERE related_entity_ids ? :entity_id ORDER BY created_at DESC LIMIT 25"""), {"entity_id":entity_id})
    return {"entity":dict(entity),"tasks":[dict(x) for x in tasks_result.mappings()],"artifacts":[dict(x) for x in artifacts_result.mappings()]}

@app.get(
    "/api/v1/entities/{entity_id}/revisions",
    tags=["Entities"],
    summary="Read entity revision history",
)
async def entity_revisions(
    entity_id: str,
    component_name: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    clause = "AND component_name = :component_name" if component_name else ""
    result = await db.execute(text(f"""
        SELECT revision_id, entity_id, revision, operation, component_name,
               payload, provenance, source_time, received_time
        FROM entity_revisions
        WHERE entity_id = :entity_id {clause}
        ORDER BY revision DESC
        LIMIT :limit
    """), {
        "entity_id": entity_id,
        "component_name": component_name,
        "limit": limit,
    })
    return [dict(row) for row in result.mappings()]



@app.get(
    "/api/v1/entities/{entity_id}/location-history",
    tags=["Entities"],
    summary="Read complete persisted entity location history",
    description=(
        "Returns the complete available latitude/longitude history for an Entity. "
        "Entity revisions are authoritative; the location projection is included "
        "as an optimized source and duplicates are removed."
    ),
)
async def location_history(
    entity_id: str,
    limit: int = Query(5000, ge=1, le=20000),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        WITH revision_locations AS (
            SELECT
                revision,
                CASE
                    WHEN component_name = 'location'
                    THEN NULLIF(payload->>'latitude','')::double precision
                    ELSE NULLIF(payload->'location'->>'latitude','')::double precision
                END AS latitude,
                CASE
                    WHEN component_name = 'location'
                    THEN NULLIF(payload->>'longitude','')::double precision
                    ELSE NULLIF(payload->'location'->>'longitude','')::double precision
                END AS longitude,
                CASE
                    WHEN component_name = 'location'
                    THEN NULLIF(payload->>'heading_degrees','')::double precision
                    ELSE NULLIF(payload->'location'->>'heading_degrees','')::double precision
                END AS heading_degrees,
                CASE
                    WHEN component_name = 'location'
                    THEN NULLIF(payload->>'speed_mps','')::double precision
                    ELSE NULLIF(payload->'location'->>'speed_mps','')::double precision
                END AS speed_mps,
                received_time AS observed_at
            FROM entity_revisions
            WHERE entity_id = :entity_id
              AND (
                (component_name = 'location' AND payload ? 'latitude' AND payload ? 'longitude')
                OR
                (component_name IS NULL AND payload ? 'location'
                 AND payload->'location' ? 'latitude'
                 AND payload->'location' ? 'longitude')
              )
        ),
        combined AS (
            SELECT revision, latitude, longitude, heading_degrees, speed_mps, observed_at
            FROM entity_location_samples
            WHERE entity_id = :entity_id
            UNION
            SELECT revision, latitude, longitude, heading_degrees, speed_mps, observed_at
            FROM revision_locations
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        )
        SELECT DISTINCT ON (revision)
            revision, latitude, longitude, heading_degrees, speed_mps, observed_at
        FROM combined
        ORDER BY revision, observed_at DESC
        LIMIT :limit
    """), {"entity_id": entity_id, "limit": limit})
    rows = list(result.mappings())
    rows.sort(key=lambda row: (row["observed_at"], row["revision"]))
    return [
        {
            "revision": row["revision"],
            "timestamp": row["observed_at"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "heading_degrees": row["heading_degrees"],
            "speed_mps": row["speed_mps"],
        }
        for row in rows
    ]

@app.post(
    "/api/v1/tasks",
    tags=["Tasks"],
    summary="Create and queue a task",
    description="Creates a durable task and appends it to the assigned agent's ordered queue.",
)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    supported = {definition["type"] for definition in TASK_DEFINITIONS}
    if body.specification.type not in supported:
        raise HTTPException(400, "Unknown task specification type")

    agent_result = await db.execute(text("""
        SELECT components FROM entities_current
        WHERE entity_id = :entity_id AND is_live = TRUE
    """), {"entity_id": body.assigned_agent_id})
    agent = agent_result.mappings().first()
    if not agent:
        raise HTTPException(400, "Assigned agent does not exist or is not live")

    definitions = (
        (agent["components"].get("task_catalog") or {}).get("definitions") or []
    )
    accepted = {
        item["type"] if isinstance(item, dict) else item
        for item in definitions
    }
    if body.specification.type not in accepted:
        raise HTTPException(409, "Assigned agent does not currently advertise this task")

    position_result = await db.execute(text("""
        SELECT COALESCE(MAX(queue_position), 0) + 1
        FROM tasks WHERE assigned_agent_id = :agent_id
    """), {"agent_id": body.assigned_agent_id})
    queue_position = int(position_result.scalar_one())

    result = await db.execute(text("""
        INSERT INTO tasks (
          description, specification, assigned_agent_id, queue_position,
          status, created_by, last_updated_by, priority, timeout_seconds,
          maximum_attempts, depends_on
        )
        VALUES (
          :description, CAST(:specification AS JSONB), :assigned_agent_id,
          :queue_position, :initial_status, :created_by, :created_by, :priority, :timeout_seconds,
          :maximum_attempts, CAST(:depends_on AS JSONB)
        )
        RETURNING *
    """), {
        "description": body.description,
        "specification": json.dumps(body.specification.model_dump()),
        "assigned_agent_id": body.assigned_agent_id,
        "queue_position": queue_position,
        "created_by": body.created_by,
        "initial_status": "STATUS_BLOCKED" if body.depends_on else "STATUS_SENT",
        "priority": body.priority,
        "timeout_seconds": body.timeout_seconds,
        "maximum_attempts": body.maximum_attempts,
        "depends_on": json.dumps([x.model_dump() for x in body.depends_on]),
    })
    task = dict(result.mappings().one())

    await db.execute(text("""
        INSERT INTO task_revisions (
          task_id, status, progress, payload, actor_id
        )
        VALUES (
          :task_id, :initial_status, 0, CAST(:payload AS JSONB), :actor_id
        )
    """), {
        "task_id": task["task_id"],
        "payload": json.dumps({"operation": "TASK_CREATED", "depends_on": [x.model_dump() for x in body.depends_on]}),
        "actor_id": body.created_by,
        "initial_status": "STATUS_BLOCKED" if body.depends_on else "STATUS_SENT",
    })
    await db.commit()
    await emit("task.created", task)
    return task

@app.get("/api/v1/tasks", tags=["Tasks"], summary="List tasks and queues")
async def list_tasks(
    assigned_agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    clause = "WHERE assigned_agent_id = :agent_id" if assigned_agent_id else ""
    result = await db.execute(text(f"""
        SELECT * FROM tasks
        {clause}
        ORDER BY assigned_agent_id, priority DESC, queue_position
    """), {"agent_id": assigned_agent_id})
    return [dict(row) for row in result.mappings()]

@app.post(
    "/api/v1/tasks/claim-next/{agent_id}",
    tags=["Tasks"],
    summary="Claim the next queued task",
    description="Plugin-facing helper that atomically claims the next eligible task for one agent.",
)
async def claim_next_task(
    agent_id: str,
    body: TaskClaim,
    db: AsyncSession = Depends(get_db),
):
    await db.execute(text("""
        UPDATE tasks t SET status='STATUS_SENT', updated_at=NOW()
        WHERE t.assigned_agent_id=:agent_id AND t.status='STATUS_BLOCKED'
          AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(t.depends_on) dep
            LEFT JOIN tasks parent ON parent.task_id=(dep->>'task_id')::uuid
            WHERE parent.task_id IS NULL OR parent.status <> COALESCE(dep->>'required_status','STATUS_DONE_OK')
          )
    """), {"agent_id": agent_id})
    await db.execute(text("""
        UPDATE tasks SET status='STATUS_TIMED_OUT', status_message='Task execution timed out', updated_at=NOW()
        WHERE assigned_agent_id=:agent_id AND status='STATUS_IN_PROGRESS' AND timeout_seconds IS NOT NULL
          AND claimed_at IS NOT NULL AND claimed_at + make_interval(secs => timeout_seconds) < NOW()
    """), {"agent_id": agent_id})

    active = await db.execute(text("""
        SELECT task_id FROM tasks
        WHERE assigned_agent_id = :agent_id
          AND status = 'STATUS_IN_PROGRESS'
        LIMIT 1
    """), {"agent_id": agent_id})
    if active.first():
        return None

    result = await db.execute(text("""
        SELECT task_id FROM tasks
        WHERE assigned_agent_id = :agent_id
          AND status = 'STATUS_SENT'
        ORDER BY priority DESC, queue_position
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    """), {"agent_id": agent_id})
    row = result.first()
    if not row:
        await db.rollback()
        return None

    updated = await db.execute(text("""
        UPDATE tasks SET
          status = 'STATUS_IN_PROGRESS',
          claimed_by = :plugin_id,
          last_updated_by = :plugin_id,
          claimed_at = NOW(),
          attempt = attempt + 1,
          updated_at = NOW()
        WHERE task_id = :task_id
        RETURNING *
    """), {"task_id": row[0], "plugin_id": body.plugin_id})
    task = dict(updated.mappings().one())
    await db.execute(text("""
        INSERT INTO task_revisions (
          task_id, status, progress, payload, actor_id
        )
        VALUES (
          :task_id, 'STATUS_IN_PROGRESS', 0,
          CAST(:payload AS JSONB), :actor_id
        )
    """), {
        "task_id": task["task_id"],
        "payload": json.dumps({"operation": "TASK_CLAIMED"}),
        "actor_id": body.plugin_id,
    })
    await db.commit()
    await emit("task.updated", task)
    return task

@app.post(
    "/api/v1/tasks/{task_id}/status",
    tags=["Tasks"],
    summary="Update task execution status",
)
async def update_task_status(
    task_id: UUID,
    body: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(text("""
        SELECT status FROM tasks WHERE task_id = :task_id
    """), {"task_id": task_id})
    current = existing.scalar_one_or_none()
    if current is None:
        raise HTTPException(404, "Task not found")
    if current in {"STATUS_DONE_OK", "STATUS_DONE_NOT_OK", "STATUS_CANCELED", "STATUS_TIMED_OUT"}:
        raise HTTPException(409, "Terminal tasks cannot be updated")

    retry_row = await db.execute(text("SELECT attempt, maximum_attempts FROM tasks WHERE task_id=:task_id"), {"task_id":task_id})
    retry_info = retry_row.mappings().one()
    effective_status = body.status.value
    effective_message = body.message
    if body.status.value == "STATUS_DONE_NOT_OK" and int(retry_info["attempt"]) < int(retry_info["maximum_attempts"]):
        effective_status = "STATUS_RETRYING"
        effective_message = body.message or "Execution failed; task queued for retry"

    result = await db.execute(text("""
        UPDATE tasks SET
          status = CASE WHEN :status='STATUS_RETRYING' THEN 'STATUS_SENT' ELSE :status END,
          progress = :progress,
          status_message = :message,
          execution = CAST(:execution AS JSONB),
          last_updated_by = :actor_id,
          updated_at = NOW()
        WHERE task_id = :task_id
        RETURNING *
    """), {
        "task_id": task_id,
        "status": effective_status,
        "progress": 0 if effective_status == "STATUS_RETRYING" else body.progress,
        "message": effective_message,
        "execution": json.dumps(body.execution),
        "actor_id": body.actor_id,
    })
    task = dict(result.mappings().one())
    await db.execute(text("""
        INSERT INTO task_revisions (
          task_id, status, progress, payload, actor_id
        )
        VALUES (
          :task_id, :status, :progress,
          CAST(:payload AS JSONB), :actor_id
        )
    """), {
        "task_id": task_id,
        "status": effective_status,
        "progress": 0 if effective_status == "STATUS_RETRYING" else body.progress,
        "payload": json.dumps({"message": effective_message, "execution": body.execution}),
        "actor_id": body.actor_id,
    })
    await db.commit()
    await emit("task.updated", task)
    return task

@app.post(
    "/api/v1/tasks/{task_id}/cancel",
    tags=["Tasks"],
    summary="Cancel a queued or active task",
)
async def cancel_task(task_id: UUID, body: TaskCancel, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(text("SELECT status FROM tasks WHERE task_id = :task_id"), {"task_id": task_id})
    current = existing.scalar_one_or_none()
    if current is None:
        raise HTTPException(404, "Task not found")
    if current in {"STATUS_DONE_OK", "STATUS_DONE_NOT_OK", "STATUS_CANCELED", "STATUS_TIMED_OUT"}:
        raise HTTPException(409, "Task is already terminal")
    result = await db.execute(text("""
        UPDATE tasks SET status='STATUS_CANCELED', status_message=:reason,
          last_updated_by=:actor_id, updated_at=NOW()
        WHERE task_id=:task_id RETURNING *
    """), {"task_id":task_id,"reason":body.reason,"actor_id":body.actor_id})
    task = dict(result.mappings().one())
    await db.execute(text("""
        INSERT INTO task_revisions(task_id,status,progress,payload,actor_id)
        VALUES(:task_id,'STATUS_CANCELED',:progress,CAST(:payload AS JSONB),:actor_id)
    """), {"task_id":task_id,"progress":task["progress"],"payload":json.dumps({"reason":body.reason}),"actor_id":body.actor_id})
    await db.commit()
    await emit("task.updated", task)
    return task

@app.get(
    "/api/v1/tasks/{task_id}/revisions",
    tags=["Tasks"],
    summary="Read task lifecycle history",
)
async def task_revisions(task_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT * FROM task_revisions
        WHERE task_id = :task_id
        ORDER BY created_at
    """), {"task_id": task_id})
    return [dict(row) for row in result.mappings()]

@app.get(
    "/api/v1/fusion/associations",
    tags=["Fusion"],
    summary="List active fusion associations",
)
async def fusion_associations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT * FROM fusion_associations ORDER BY updated_at DESC
    """))
    return [dict(row) for row in result.mappings()]


@app.post("/api/v1/plugins/register", tags=["Plugins"])
async def register_plugin(body: PluginRegister, db: AsyncSession = Depends(get_db)):
    result=await db.execute(text("""
    INSERT INTO plugins(plugin_id,name,version,plugin_type,protocol,capabilities,configuration_schema,configuration,status,last_heartbeat)
    VALUES(:plugin_id,:name,:version,:plugin_type,:protocol,CAST(:capabilities AS JSONB),CAST(:schema AS JSONB),CAST(:configuration AS JSONB),'REGISTERED',NOW())
    ON CONFLICT(plugin_id) DO UPDATE SET name=EXCLUDED.name,version=EXCLUDED.version,plugin_type=EXCLUDED.plugin_type,protocol=EXCLUDED.protocol,capabilities=EXCLUDED.capabilities,configuration_schema=EXCLUDED.configuration_schema,configuration=plugins.configuration||EXCLUDED.configuration,updated_at=NOW()
    RETURNING *"""),{"plugin_id":body.plugin_id,"name":body.name,"version":body.version,"plugin_type":body.plugin_type,"protocol":body.protocol,"capabilities":json.dumps(body.capabilities),"schema":json.dumps(body.configuration_schema),"configuration":json.dumps(body.configuration)})
    plugin=dict(result.mappings().one());await db.commit();await hub.broadcast({"type":"plugin.updated","data":plugin});return plugin

@app.get("/api/v1/plugins", tags=["Plugins"])
async def list_plugins(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(text("SELECT * FROM plugins ORDER BY name"))
        return [dict(row) for row in result.mappings()]
    except Exception as exc:
        await db.rollback()
        raise HTTPException(500, f"Plugin registry unavailable: {exc}")

@app.get("/api/v1/plugins/{plugin_id}", tags=["Plugins"])
async def get_plugin(plugin_id:str,db:AsyncSession=Depends(get_db)):
    result=await db.execute(text("SELECT * FROM plugins WHERE plugin_id=:id"),{"id":plugin_id});row=result.mappings().first()
    if not row: raise HTTPException(404,"Plugin not found")
    return dict(row)

@app.post("/api/v1/plugins/{plugin_id}/heartbeat", tags=["Plugins"])
async def heartbeat(plugin_id:str,body:PluginHeartbeat,db:AsyncSession=Depends(get_db)):
    result=await db.execute(text("UPDATE plugins SET status=:status,status_message=:message,metrics=CAST(:metrics AS JSONB),last_heartbeat=NOW(),updated_at=NOW() WHERE plugin_id=:id RETURNING *"),{"id":plugin_id,"status":body.status,"message":body.message,"metrics":json.dumps(body.metrics)});row=result.mappings().first()
    if not row: raise HTTPException(404,"Plugin not registered")
    plugin=dict(row);await db.commit();await hub.broadcast({"type":"plugin.updated","data":plugin});return plugin

@app.patch("/api/v1/plugins/{plugin_id}/configuration", tags=["Plugins"])
async def plugin_configuration(plugin_id:str,body:PluginConfigurationPatch,db:AsyncSession=Depends(get_db)):
    result=await db.execute(text("UPDATE plugins SET configuration=CAST(:configuration AS JSONB),updated_at=NOW() WHERE plugin_id=:id RETURNING *"),{"id":plugin_id,"configuration":json.dumps(body.configuration)});row=result.mappings().first()
    if not row: raise HTTPException(404,"Plugin not found")
    plugin=dict(row);await db.commit();await hub.broadcast({"type":"plugin.updated","data":plugin});return plugin

@app.post("/api/v1/plugins/{plugin_id}/enable", tags=["Plugins"])
async def enable_plugin(plugin_id:str,db:AsyncSession=Depends(get_db)):
    result=await db.execute(text("UPDATE plugins SET enabled=TRUE,status='REGISTERED',updated_at=NOW() WHERE plugin_id=:id RETURNING *"),{"id":plugin_id});row=result.mappings().first()
    if not row: raise HTTPException(404,"Plugin not found")
    plugin=dict(row);await db.commit();await hub.broadcast({"type":"plugin.updated","data":plugin});return plugin

@app.post("/api/v1/plugins/{plugin_id}/disable", tags=["Plugins"])
async def disable_plugin(plugin_id:str,db:AsyncSession=Depends(get_db)):
    result=await db.execute(text("UPDATE plugins SET enabled=FALSE,status='DISABLED',updated_at=NOW() WHERE plugin_id=:id RETURNING *"),{"id":plugin_id});row=result.mappings().first()
    if not row: raise HTTPException(404,"Plugin not found")
    plugin=dict(row);await db.commit();await hub.broadcast({"type":"plugin.updated","data":plugin});return plugin

@app.post("/api/v1/plugins/{plugin_id}/logs", tags=["Plugins"])
async def add_plugin_log(plugin_id:str,body:PluginLogCreate,db:AsyncSession=Depends(get_db)):
    await db.execute(text("INSERT INTO plugin_logs(plugin_id,level,message,details) VALUES(:id,:level,:message,CAST(:details AS JSONB))"),{"id":plugin_id,"level":body.level,"message":body.message,"details":json.dumps(body.details)});await db.commit();return {"status":"accepted"}

@app.get("/api/v1/plugins/{plugin_id}/logs", tags=["Plugins"])
async def get_plugin_logs(plugin_id:str,limit:int=Query(200,ge=1,le=2000),db:AsyncSession=Depends(get_db)):
    result=await db.execute(text("SELECT * FROM plugin_logs WHERE plugin_id=:id ORDER BY created_at DESC LIMIT :limit"),{"id":plugin_id,"limit":limit});return [dict(x) for x in result.mappings()]

@app.post("/api/v1/artifacts/text", tags=["Artifacts"])
async def create_text_artifact(body:ArtifactCreateText,db:AsyncSession=Depends(get_db)):
    artifact_id=str((await db.execute(text("SELECT gen_random_uuid()"))).scalar_one());object_name=f"{artifact_id}/{body.name}";data=body.content.encode();size,digest=put_bytes(object_name,data,body.content_type)
    result=await db.execute(text("""INSERT INTO artifacts(artifact_id,name,artifact_type,content_type,object_name,size_bytes,sha256,related_entity_ids,related_task_ids,related_plugin_id,metadata) VALUES(:id,:name,:type,:content_type,:object_name,:size,:sha,CAST(:entities AS JSONB),CAST(:tasks AS JSONB),:plugin,CAST(:metadata AS JSONB)) RETURNING *"""),{"id":artifact_id,"name":body.name,"type":body.artifact_type,"content_type":body.content_type,"object_name":object_name,"size":size,"sha":digest,"entities":json.dumps(body.related_entity_ids),"tasks":json.dumps(body.related_task_ids),"plugin":body.related_plugin_id,"metadata":json.dumps(body.metadata)})
    artifact=dict(result.mappings().one());await db.commit();await hub.broadcast({"type":"artifact.created","data":artifact});return artifact

@app.get("/api/v1/artifacts", tags=["Artifacts"])
async def list_artifacts(db:AsyncSession=Depends(get_db)):
    result=await db.execute(text("SELECT * FROM artifacts ORDER BY created_at DESC"));return [dict(x) for x in result.mappings()]

@app.get("/api/v1/artifacts/{artifact_id}", tags=["Artifacts"])
async def artifact_metadata(artifact_id:UUID,db:AsyncSession=Depends(get_db)):
    result=await db.execute(text("SELECT * FROM artifacts WHERE artifact_id=:id"),{"id":artifact_id})
    row=result.mappings().first()
    if not row: raise HTTPException(404,"Artifact not found")
    return dict(row)

@app.get("/api/v1/artifacts/{artifact_id}/content", tags=["Artifacts"])
async def artifact_content(artifact_id:UUID,db:AsyncSession=Depends(get_db)):
    result=await db.execute(text("SELECT object_name,content_type,name FROM artifacts WHERE artifact_id=:id"),{"id":artifact_id});row=result.mappings().first()
    if not row: raise HTTPException(404,"Artifact not found")
    obj=get_object(row['object_name']);return StreamingResponse(obj.stream(32768),media_type=row['content_type'],headers={"Content-Disposition":f"attachment; filename={row['name']}"})

@app.websocket("/api/v1/stream")
async def stream(ws: WebSocket):
    await hub.connect(ws)
    try:
        await ws.send_json({
            "type": "stream.ready",
            "data": {"message": "OpenGrid live stream connected"},
        })
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception:
        await hub.disconnect(ws)
