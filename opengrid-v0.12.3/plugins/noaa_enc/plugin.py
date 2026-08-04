import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

PLUGIN_ID = os.getenv("PLUGIN_ID", "opengrid.noaa_enc")
API_URL = os.getenv("OPENGRID_API_URL", "http://api:8000").rstrip("/")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://opengrid:opengrid@postgres:5432/opengrid")
PUBLIC_BASE_URL = os.getenv("PLUGIN_PUBLIC_BASE_URL", "http://noaa-enc-plugin:8090").rstrip("/")
DEFAULT_SERVICE = os.getenv(
    "NOAA_ENC_SERVICE_URL",
    "https://encdirect.noaa.gov/arcgis/rest/services/encdirect/enc_harbour/MapServer",
).rstrip("/")

DEFAULT_CONFIG = {
    "service_url": DEFAULT_SERVICE,
    "auto_discover": True,
    "default_visible": True,
    "max_features_per_layer": 5000,
    "refresh_seconds": 900,
    "disabled_layers": [],
    "preferred_layers": [],
}

pool: asyncpg.Pool | None = None
metrics: dict[str, Any] = {
    "layers_discovered": 0,
    "features_cached": 0,
    "last_discovery": None,
    "last_query": None,
}
layer_catalog: dict[str, dict[str, Any]] = {}


def safe_layer_id(name: str, remote_id: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{remote_id}-{slug}"[:120]


def style_for(name: str, geometry_type: str) -> dict[str, Any]:
    n = name.lower()
    if "depth area" in n:
        return {"fillColor": "#176b87", "fillOpacity": 0.22, "lineColor": "#45a9c8"}
    if "land" in n or "coast" in n:
        return {"fillColor": "#7d7258", "fillOpacity": 0.45, "lineColor": "#c4b98f"}
    if "contour" in n:
        return {"lineColor": "#65c8e8", "lineWidth": 1.2}
    if "wreck" in n or "obstruction" in n:
        return {"circleColor": "#ff6f61", "circleRadius": 5}
    if "buoy" in n or "beacon" in n or "light" in n:
        return {"circleColor": "#ffd65c", "circleRadius": 4}
    if geometry_type.lower().endswith("polygon"):
        return {"fillColor": "#41829a", "fillOpacity": 0.18, "lineColor": "#6db7ce"}
    if geometry_type.lower().endswith("line"):
        return {"lineColor": "#6db7ce", "lineWidth": 1.2}
    return {"circleColor": "#dff8ff", "circleRadius": 3}


async def api(method: str, path: str, **kwargs):
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.request(method, f"{API_URL}{path}", **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None


async def get_config() -> dict[str, Any]:
    try:
        plugin = await api("GET", f"/api/v1/plugins/{PLUGIN_ID}")
        config = dict(DEFAULT_CONFIG)
        config.update(plugin.get("configuration") or {})
        return config
    except Exception:
        return dict(DEFAULT_CONFIG)


async def ensure_storage():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS plugin_noaa_enc")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_noaa_enc.layers(
                layer_id TEXT PRIMARY KEY,
                remote_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                geometry_type TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_noaa_enc.features(
                layer_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                properties JSONB NOT NULL DEFAULT '{}'::jsonb,
                geom geometry(Geometry,4326) NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(layer_id, source_id)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS noaa_enc_features_geom_idx ON plugin_noaa_enc.features USING GIST(geom)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_noaa_enc.ingest_jobs(
                job_id BIGSERIAL PRIMARY KEY,
                layer_id TEXT,
                bbox TEXT,
                status TEXT NOT NULL,
                feature_count INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ
            )
        """)


async def register_plugin():
    await api("POST", "/api/v1/plugins/register", json={
        "plugin_id": PLUGIN_ID,
        "name": "NOAA ENC",
        "version": "0.12.3",
        "plugin_type": "GIS_DATA_SOURCE",
        "protocol": "ArcGIS REST / GeoJSON",
        "capabilities": [
            "gis.layer_provider", "gis.feature_query", "gis.local_cache",
            "gis.dataset_discovery", "plugin.storage.postgis",
        ],
        "configuration_schema": {
            "type": "object",
            "properties": {
                "service_url": {"type": "string", "title": "NOAA ENC ArcGIS MapServer"},
                "auto_discover": {"type": "boolean", "title": "Discover layers automatically"},
                "default_visible": {"type": "boolean", "title": "Show preferred ENC layers by default"},
                "max_features_per_layer": {"type": "integer", "minimum": 100, "maximum": 10000},
                "refresh_seconds": {"type": "integer", "minimum": 60},
                "disabled_layers": {"type": "array", "title": "Hidden ENC layers", "description": "Uncheck layers to hide them from the operational map.", "items": {"type": "string", "enum": []}},
                "preferred_layers": {"type": "array", "title": "Discovery name filters", "description": "Only discover layers whose names match one of these values. Leave empty to discover every supported feature layer.", "items": {"type": "string"}},
            },
        },
        "configuration": DEFAULT_CONFIG,
    })


async def discover_layers():
    config = await get_config()
    url = f"{str(config['service_url']).rstrip('/')}"
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.get(url, params={"f": "pjson"})
        response.raise_for_status()
        service = response.json()
    preferred = [str(x).lower() for x in config.get("preferred_layers", [])]
    discovered = []
    for remote in service.get("layers", []):
        name = str(remote.get("name", f"Layer {remote.get('id')}"))
        if preferred and not any(keyword in name.lower() for keyword in preferred):
            continue
        remote_id = int(remote["id"])
        detail_url = f"{url}/{remote_id}"
        geometry_type = "mixed"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                detail = (await client.get(detail_url, params={"f": "pjson"})).json()
                geometry_type = str(detail.get("geometryType") or "mixed").replace("esriGeometry", "")
                if detail.get("subLayerIds") or (detail.get("type") and "feature" not in str(detail.get("type")).lower()):
                    continue
        except Exception:
            detail = {}
        layer_id = safe_layer_id(name, remote_id)
        info = {
            "layer_id": layer_id,
            "remote_id": remote_id,
            "name": name,
            "geometry_type": geometry_type,
            "query_url": f"{detail_url}/query",
            "style": style_for(name, geometry_type),
            "metadata": {"source_layer": remote_id, "source_service": url, "fields": detail.get("fields", [])},
        }
        layer_catalog[layer_id] = info
        discovered.append(info)
        assert pool
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO plugin_noaa_enc.layers(layer_id,remote_id,name,geometry_type,metadata,discovered_at)
                VALUES($1,$2,$3,$4,$5::jsonb,NOW())
                ON CONFLICT(layer_id) DO UPDATE SET remote_id=EXCLUDED.remote_id,name=EXCLUDED.name,
                    geometry_type=EXCLUDED.geometry_type,metadata=EXCLUDED.metadata,discovered_at=NOW()
            """, layer_id, remote_id, name, geometry_type, json.dumps(info["metadata"]))
    disabled = {str(x) for x in config.get("disabled_layers", [])}
    # Refresh the configuration schema with the actual discovered layer names so
    # the generic plugin form can render layer visibility as checkboxes.
    await api("POST", "/api/v1/plugins/register", json={
        "plugin_id": PLUGIN_ID, "name": "NOAA ENC", "version": "0.12.3",
        "plugin_type": "GIS_DATA_SOURCE", "protocol": "ArcGIS REST / GeoJSON",
        "capabilities": ["gis.layer_provider", "gis.feature_query", "gis.local_cache", "gis.dataset_discovery", "plugin.storage.postgis"],
        "configuration_schema": {"type": "object", "properties": {
            "service_url": {"type": "string", "title": "NOAA ENC ArcGIS MapServer"},
            "auto_discover": {"type": "boolean", "title": "Discover layers automatically"},
            "default_visible": {"type": "boolean", "title": "Display ENC data by default"},
            "max_features_per_layer": {"type": "integer", "title": "Maximum features per layer", "minimum": 100, "maximum": 10000},
            "refresh_seconds": {"type": "integer", "title": "Layer discovery interval (seconds)", "minimum": 60},
            "disabled_layers": {"type": "array", "title": "Hidden ENC layers", "description": "Checked entries are hidden from the map.", "items": {"type": "string", "enum": [x["name"] for x in discovered]}},
            "preferred_layers": {"type": "array", "title": "Discovery name filters", "description": "Leave empty to discover every supported feature layer.", "items": {"type": "string"}},
        }},
        "configuration": config,
    })
    await api("PUT", f"/api/v1/plugins/{PLUGIN_ID}/gis-layers", json={"layers": [
        {
            "layer_id": x["layer_id"], "name": x["name"],
            "description": "NOAA ENC Direct to GIS feature layer",
            "geometry_type": x["geometry_type"],
            "service_url": f"{PUBLIC_BASE_URL}/layers/{x['layer_id']}.geojson",
            "default_visible": bool(config.get("default_visible", True)) and x["name"] not in disabled,
            "min_zoom": 8, "max_zoom": 24, "style": x["style"], "metadata": x["metadata"],
        } for x in discovered if x["name"] not in disabled
    ]})
    metrics["layers_discovered"] = len(discovered)
    metrics["last_discovery"] = datetime.now(timezone.utc).isoformat()


async def cache_features(layer: dict[str, Any], collection: dict[str, Any]):
    assert pool
    count = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for idx, feature in enumerate(collection.get("features") or []):
                geometry = feature.get("geometry")
                if not geometry:
                    continue
                props = feature.get("properties") or {}
                source_id = str(props.get("OBJECTID") or props.get("FID") or props.get("RCID") or idx)
                await conn.execute("""
                    INSERT INTO plugin_noaa_enc.features(layer_id,source_id,properties,geom,observed_at)
                    VALUES($1,$2,$3::jsonb,ST_SetSRID(ST_GeomFromGeoJSON($4),4326),NOW())
                    ON CONFLICT(layer_id,source_id) DO UPDATE SET properties=EXCLUDED.properties,
                        geom=EXCLUDED.geom,observed_at=NOW()
                """, layer["layer_id"], source_id, json.dumps(props), json.dumps(geometry))
                count += 1
    metrics["features_cached"] = int(metrics.get("features_cached", 0)) + count
    return count


async def query_remote(layer: dict[str, Any], bbox: str, max_features: int) -> dict[str, Any]:
    params = {
        "f": "geojson", "where": "1=1", "outFields": "*", "returnGeometry": "true",
        "geometry": bbox, "geometryType": "esriGeometryEnvelope", "inSR": "4326",
        "outSR": "4326", "spatialRel": "esriSpatialRelIntersects",
        "resultRecordCount": str(max_features),
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(layer["query_url"], params=params)
        response.raise_for_status()
        data = response.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data


async def read_cache(layer_id: str, bbox: str) -> dict[str, Any]:
    values = [float(x) for x in bbox.split(",")]
    if len(values) != 4:
        raise ValueError("bbox must be west,south,east,north")
    assert pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT source_id,properties,ST_AsGeoJSON(geom)::json AS geometry
            FROM plugin_noaa_enc.features
            WHERE layer_id=$1 AND geom && ST_MakeEnvelope($2,$3,$4,$5,4326)
            LIMIT 10000
        """, layer_id, *values)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": r["source_id"], "properties": dict(r["properties"]), "geometry": r["geometry"]}
        for r in rows
    ]}


async def heartbeat_loop():
    while True:
        try:
            await api("POST", f"/api/v1/plugins/{PLUGIN_ID}/heartbeat", json={
                "status": "RUNNING", "message": f"{metrics['layers_discovered']} ENC layers available", "metrics": metrics,
            })
        except Exception as exc:
            print("[noaa-enc] heartbeat:", exc)
        await asyncio.sleep(10)


async def discovery_loop():
    while True:
        try:
            await discover_layers()
        except Exception as exc:
            print("[noaa-enc] discovery:", exc)
        config = await get_config()
        await asyncio.sleep(max(60, int(config.get("refresh_seconds", 900))))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_storage()
    while True:
        try:
            await register_plugin()
            break
        except Exception as exc:
            print("[noaa-enc] waiting for API:", exc)
            await asyncio.sleep(3)
    tasks = [asyncio.create_task(heartbeat_loop()), asyncio.create_task(discovery_loop())]
    yield
    for task in tasks:
        task.cancel()
    if pool:
        await pool.close()


app = FastAPI(title="OpenGrid NOAA ENC Plugin", version="0.12.3", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "plugin_id": PLUGIN_ID, "metrics": metrics}


@app.get("/layers")
async def layers():
    return list(layer_catalog.values())


@app.get("/layers/{layer_id}.geojson")
async def layer_geojson(layer_id: str, bbox: str = Query(...)):
    layer = layer_catalog.get(layer_id)
    if not layer:
        raise HTTPException(404, "ENC layer not found")
    config = await get_config()
    try:
        collection = await query_remote(layer, bbox, int(config.get("max_features_per_layer", 5000)))
        await cache_features(layer, collection)
        metrics["last_query"] = datetime.now(timezone.utc).isoformat()
        return JSONResponse(collection, media_type="application/geo+json")
    except Exception as exc:
        cached = await read_cache(layer_id, bbox)
        if cached["features"]:
            return JSONResponse(cached, media_type="application/geo+json", headers={"X-OpenGrid-Cache": "stale"})
        raise HTTPException(502, f"NOAA ENC query failed and no cached features are available: {exc}")
