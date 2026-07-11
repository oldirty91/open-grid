import json
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.events import event_bus
from app.fusion import correlate_track
from app.models import (
    ComponentPatch,
    EntityUpsert,
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
    {"name": "System", "description": "Health and task definition discovery."},
]

TASK_DEFINITIONS = [
    {
        "type": "opengrid.tasks.v1.Navigate",
        "display_name": "Navigate",
        "objective_types": ["POINT"],
        "parameter_schema": {
            "type": "object",
            "properties": {
                "speed_mps": {"type": "number", "minimum": 0, "default": 3.0},
                "arrival_radius_m": {"type": "number", "minimum": 1, "default": 20},
            },
        },
    },
    {
        "type": "opengrid.tasks.v1.Investigate",
        "display_name": "Investigate",
        "objective_types": ["ENTITY", "POINT"],
        "parameter_schema": {
            "type": "object",
            "properties": {
                "speed_mps": {"type": "number", "minimum": 0, "default": 3.0},
                "standoff_m": {"type": "number", "minimum": 0, "default": 50},
            },
        },
    },
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    await event_bus.connect()
    yield
    await event_bus.close()

app = FastAPI(
    title="OpenGrid API",
    version="0.3.2",
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

async def emit(kind: str, data: dict):
    await event_bus.publish(kind.replace(":", "."), data)
    await hub.broadcast({"type": kind, "data": data})

@app.get("/health", tags=["System"], summary="Service health")
async def health():
    return {"status": "ok", "service": "opengrid-api", "version": "0.3.2"}

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
    summary="Read entity location history",
)
async def location_history(
    entity_id: str,
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        SELECT revision, payload, received_time
        FROM entity_revisions
        WHERE entity_id = :entity_id
          AND (component_name = 'location' OR (component_name IS NULL AND payload ? 'location'))
        ORDER BY revision DESC
        LIMIT :limit
    """), {"entity_id": entity_id, "limit": limit})
    rows = list(result.mappings())
    samples = []
    for row in reversed(rows):
        payload = row["payload"]
        location = payload if isinstance(payload, dict) and "latitude" in payload else payload.get("location", {})
        if location.get("latitude") is None or location.get("longitude") is None:
            continue
        samples.append({
            "revision": row["revision"],
            "timestamp": row["received_time"],
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "heading_degrees": location.get("heading_degrees"),
            "speed_mps": location.get("speed_mps"),
        })
    return samples

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
          status, created_by, last_updated_by
        )
        VALUES (
          :description, CAST(:specification AS JSONB), :assigned_agent_id,
          :queue_position, 'STATUS_SENT', :created_by, :created_by
        )
        RETURNING *
    """), {
        "description": body.description,
        "specification": json.dumps(body.specification.model_dump()),
        "assigned_agent_id": body.assigned_agent_id,
        "queue_position": queue_position,
        "created_by": body.created_by,
    })
    task = dict(result.mappings().one())

    await db.execute(text("""
        INSERT INTO task_revisions (
          task_id, status, progress, payload, actor_id
        )
        VALUES (
          :task_id, 'STATUS_SENT', 0, CAST(:payload AS JSONB), :actor_id
        )
    """), {
        "task_id": task["task_id"],
        "payload": json.dumps({"operation": "TASK_CREATED"}),
        "actor_id": body.created_by,
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
        ORDER BY assigned_agent_id, queue_position
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
        ORDER BY queue_position
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
    if current in {"STATUS_DONE_OK", "STATUS_DONE_NOT_OK", "STATUS_CANCELED"}:
        raise HTTPException(409, "Terminal tasks cannot be updated")

    result = await db.execute(text("""
        UPDATE tasks SET
          status = :status,
          progress = :progress,
          status_message = :message,
          last_updated_by = :actor_id,
          updated_at = NOW()
        WHERE task_id = :task_id
        RETURNING *
    """), {
        "task_id": task_id,
        "status": body.status.value,
        "progress": body.progress,
        "message": body.message,
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
        "status": body.status.value,
        "progress": body.progress,
        "payload": json.dumps({"message": body.message}),
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
    if current in {"STATUS_DONE_OK", "STATUS_DONE_NOT_OK", "STATUS_CANCELED"}:
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
