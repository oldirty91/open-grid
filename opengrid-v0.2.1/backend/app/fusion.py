import hashlib
import json
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings

def location_of(components: dict[str, Any]) -> tuple[float, float] | None:
    location = components.get("location") or {}
    lat = location.get("latitude")
    lon = location.get("longitude")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)

def source_of(components: dict[str, Any]) -> str:
    return str((components.get("provenance") or {}).get("source_system") or "unknown")

def stable_fused_id(ids: list[str]) -> str:
    digest = hashlib.sha256("|".join(sorted(ids)).encode()).hexdigest()[:16]
    return f"fused-track-{digest}"

async def correlate_track(session: AsyncSession, entity_id: str, components: dict[str, Any]):
    point = location_of(components)
    if not point:
        return None

    lat, lon = point
    source = source_of(components)
    result = await session.execute(text("""
        SELECT entity_id, components,
               ST_Distance(
                 geom::geography,
                 ST_SetSRID(ST_Point(:lon,:lat),4326)::geography
               ) AS distance_m
        FROM entities_current
        WHERE is_live = TRUE
          AND template = 'TRACK'
          AND entity_id <> :entity_id
          AND COALESCE(components->'ontology'->>'track_type','SOURCE') <> 'FUSED'
          AND COALESCE(components->'provenance'->>'source_system','unknown') <> :source
          AND updated_at > NOW() - (:max_age || ' seconds')::interval
          AND geom IS NOT NULL
          AND ST_DWithin(
            geom::geography,
            ST_SetSRID(ST_Point(:lon,:lat),4326)::geography,
            :gate_m
          )
        ORDER BY distance_m
        LIMIT 1
    """), {
        "entity_id": entity_id,
        "source": source,
        "lat": lat,
        "lon": lon,
        "gate_m": settings.fusion_gate_m,
        "max_age": settings.fusion_max_age_s,
    })
    candidate = result.mappings().first()
    if not candidate:
        return None

    other_id = candidate["entity_id"]
    other_components = candidate["components"]
    other_point = location_of(other_components)
    if not other_point:
        return None

    source_ids = sorted([entity_id, other_id])
    fused_id = stable_fused_id(source_ids)
    distance_m = float(candidate["distance_m"])
    score = max(0.0, 1.0 - distance_m / settings.fusion_gate_m)
    fused_lat = (lat + other_point[0]) / 2
    fused_lon = (lon + other_point[1]) / 2

    fused_components = {
        "aliases": {"name": f"Fused Contact {fused_id[-6:].upper()}"},
        "ontology": {
            "template": "TRACK",
            "domain": "MARITIME",
            "track_type": "FUSED",
        },
        "location": {"latitude": fused_lat, "longitude": fused_lon},
        "mil_view": {"disposition": "UNKNOWN"},
        "provenance": {
            "source_system": "opengrid-fusion",
            "algorithm": "nearest-neighbor-v0",
            "confidence": round(score, 3),
        },
        "relationships": {"derived_from": source_ids},
        "fusion": {
            "association_score": round(score, 3),
            "separation_m": round(distance_m, 2),
            "gate_m": settings.fusion_gate_m,
        },
    }

    current = await session.execute(text("""
        INSERT INTO entities_current (
          entity_id, revision, is_live, template, components,
          component_provenance, geom
        )
        VALUES (
          :entity_id, 1, TRUE, 'TRACK', CAST(:components AS JSONB),
          CAST(:provenance AS JSONB),
          ST_SetSRID(ST_Point(:lon,:lat),4326)
        )
        ON CONFLICT (entity_id) DO UPDATE SET
          revision = entities_current.revision + 1,
          components = EXCLUDED.components,
          component_provenance = EXCLUDED.component_provenance,
          geom = EXCLUDED.geom,
          updated_at = NOW()
        RETURNING revision
    """), {
        "entity_id": fused_id,
        "components": json.dumps(fused_components),
        "provenance": json.dumps({"*": {"source_system": "opengrid-fusion"}}),
        "lat": fused_lat,
        "lon": fused_lon,
    })
    revision = current.scalar_one()

    await session.execute(text("""
        INSERT INTO entity_revisions (
          entity_id, revision, operation, payload, provenance
        )
        VALUES (
          :entity_id, :revision, 'FUSION_PROJECTION',
          CAST(:payload AS JSONB), CAST(:provenance AS JSONB)
        )
    """), {
        "entity_id": fused_id,
        "revision": revision,
        "payload": json.dumps(fused_components),
        "provenance": json.dumps({"source_system": "opengrid-fusion"}),
    })

    await session.execute(text("""
        INSERT INTO fusion_associations (
          fused_entity_id, source_entity_ids, algorithm, score, details
        )
        VALUES (
          :fused_id, CAST(:sources AS JSONB),
          'nearest-neighbor-v0', :score, CAST(:details AS JSONB)
        )
        ON CONFLICT (fused_entity_id) DO UPDATE SET
          source_entity_ids = EXCLUDED.source_entity_ids,
          score = EXCLUDED.score,
          details = EXCLUDED.details,
          updated_at = NOW()
    """), {
        "fused_id": fused_id,
        "sources": json.dumps(source_ids),
        "score": score,
        "details": json.dumps({"distance_m": distance_m}),
    })

    return {
        "fused_entity_id": fused_id,
        "source_entity_ids": source_ids,
        "score": score,
        "entity": {
            "entity_id": fused_id,
            "revision": revision,
            "is_live": True,
            "template": "TRACK",
            "components": fused_components,
        },
    }
