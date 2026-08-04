import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

PLUGIN_ID = os.getenv("PLUGIN_ID", "opengrid.noaa_enc")
API_URL = os.getenv("OPENGRID_API_URL", "http://api:8000").rstrip("/")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://opengrid:opengrid@postgres:5432/opengrid")
PUBLIC_BASE_URL = os.getenv("PLUGIN_PUBLIC_BASE_URL", "http://noaa-enc-plugin:8090").rstrip("/")
DATA_DIR = Path(os.getenv("ENC_DATA_DIR", "/data/enc"))
CONVERTED_DIR = DATA_DIR / "converted"
SOURCE_MODE = os.getenv("ENC_SOURCE_MODE", "local").lower()

DEFAULT_CONFIG = {
    "import_on_startup": True,
    "default_visible": True,
    "max_features_per_layer": 10000,
    "refresh_seconds": 120,
    "disabled_classes": [],
}

pool: asyncpg.Pool | None = None
metrics: dict[str, Any] = {
    "layers_discovered": 0,
    "features_cached": 0,
    "local_files": 0,
    "s57_cells": 0,
    "last_discovery": None,
    "last_import": None,
    "last_error": None,
}
layer_catalog: dict[str, dict[str, Any]] = {}
_discovery_lock = asyncio.Lock()


def safe_layer_id(name: str, source_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "layer"
    digest = hashlib.sha1(f"{source_name}:{name}".encode()).hexdigest()[:10]
    return f"local-{digest}-{slug}"[:120]


def style_for(name: str, geometry_type: str) -> dict[str, Any]:
    n = name.lower()
    if "depare" in n or "depth area" in n:
        return {"fillColor": "#176b87", "fillOpacity": 0.22, "lineColor": "#45a9c8"}
    if "lndare" in n or "land" in n or "coast" in n:
        return {"fillColor": "#7d7258", "fillOpacity": 0.45, "lineColor": "#c4b98f"}
    if "depcnt" in n or "contour" in n:
        return {"lineColor": "#65c8e8", "lineWidth": 1.2}
    if "wreck" in n or "obstrn" in n or "obstruction" in n:
        return {"circleColor": "#ff6f61", "circleRadius": 5}
    if any(x in n for x in ("boy", "bcn", "light")):
        return {"circleColor": "#ffd65c", "circleRadius": 5}
    g = geometry_type.lower()
    if "polygon" in g:
        return {"fillColor": "#41829a", "fillOpacity": 0.18, "lineColor": "#6db7ce"}
    if "line" in g:
        return {"lineColor": "#6db7ce", "lineWidth": 1.2}
    return {"circleColor": "#dff8ff", "circleRadius": 4}


async def api(method: str, path: str, **kwargs):
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.request(method, f"{API_URL}{path}", **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None


async def get_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    try:
        plugin = await api("GET", f"/api/v1/plugins/{PLUGIN_ID}")
        config.update(plugin.get("configuration") or {})
    except Exception:
        pass
    known = set(DEFAULT_CONFIG)
    return {key: config.get(key, DEFAULT_CONFIG[key]) for key in known}


async def ensure_storage():
    global pool
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS plugin_noaa_enc")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_noaa_enc.layers(
                layer_id TEXT PRIMARY KEY,
                remote_id INTEGER NOT NULL DEFAULT -1,
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
            CREATE TABLE IF NOT EXISTS plugin_noaa_enc.datasets(
                filename TEXT PRIMARY KEY,
                source_format TEXT NOT NULL,
                size_bytes BIGINT NOT NULL DEFAULT 0,
                imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                status TEXT NOT NULL DEFAULT 'READY',
                layer_count INTEGER NOT NULL DEFAULT 0,
                message TEXT
            )
        """)


async def register_plugin(config: dict[str, Any] | None = None):
    config = config or await get_config()
    await api("POST", "/api/v1/plugins/register", json={
        "plugin_id": PLUGIN_ID,
        "name": "NOAA ENC",
        "version": "0.13.4",
        "plugin_type": "GIS_DATA_SOURCE",
        "protocol": "Local S-57 / GeoJSON",
        "capabilities": [
            "gis.layer_provider", "gis.feature_query", "gis.local_cache",
            "gis.s57_import", "gis.file_import", "plugin.storage.postgis",
        ],
        "configuration_schema": {
            "type": "object",
            "properties": {
                "import_on_startup": {"type": "boolean", "title": "Import local files on startup"},
                "default_visible": {"type": "boolean", "title": "Display imported ENC layers by default"},
                "max_features_per_layer": {"type": "integer", "title": "Maximum visible features per layer", "minimum": 100, "maximum": 50000},
                "refresh_seconds": {"type": "integer", "title": "Local directory rescan interval (seconds)", "minimum": 30},
                "disabled_classes": {
                    "type": "array", "title": "Hidden ENC classes",
                    "description": "Classes hidden from the map. Use the feature inspector to add entries quickly.",
                    "items": {"type": "string"}
                },
            },
        },
        "configuration": config,
    })
    # Registration preserves existing values for normal adapters. This local-only
    # plugin explicitly replaces old remote-era keys so the UI reflects reality.
    await api("PATCH", f"/api/v1/plugins/{PLUGIN_ID}/configuration", json={"configuration": config})


def _run(command: list[str], timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def _s57_layer_names(path: Path) -> list[str]:
    result = _run(["ogrinfo", "-ro", str(path)], timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ogrinfo failed")
    names: list[str] = []
    for line in result.stdout.splitlines():
        match = re.match(r"\s*\d+\s*:\s*([^\s(]+)", line)
        if match:
            name = match.group(1).strip()
            if name and name not in names:
                names.append(name)
    return names


def convert_s57(path: Path, force: bool = False) -> dict[str, Any]:
    target = CONVERTED_DIR / path.stem
    marker = target / ".source-mtime"
    stamp = str(path.stat().st_mtime_ns)
    if target.exists() and marker.exists() and marker.read_text().strip() == stamp and not force:
        return {"filename": path.name, "converted": False, "layers": len(list(target.glob("*.geojson"))), "message": "Already current"}
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    names = _s57_layer_names(path)
    converted = 0
    failures: list[str] = []
    env_options = "RETURN_PRIMITIVES=OFF,RETURN_LINKAGES=OFF,LNAM_REFS=ON"
    for layer_name in names:
        output = target / f"{layer_name}.geojson"
        result = _run([
            "ogr2ogr", "-f", "GeoJSON", "-t_srs", "EPSG:4326", "-skipfailures",
            "--config", "OGR_S57_OPTIONS", env_options,
            str(output), str(path), layer_name,
        ], timeout=300)
        if result.returncode == 0 and output.exists() and output.stat().st_size > 50:
            try:
                data = json.loads(output.read_text(encoding="utf-8"))
                if data.get("features"):
                    converted += 1
                else:
                    output.unlink(missing_ok=True)
            except Exception:
                output.unlink(missing_ok=True)
        elif result.stderr.strip():
            failures.append(f"{layer_name}: {result.stderr.strip()[:160]}")
    marker.write_text(stamp)
    if not converted:
        raise RuntimeError("No feature layers were converted from the ENC cell" + (f": {failures[0]}" if failures else ""))
    return {"filename": path.name, "converted": True, "layers": converted, "message": f"Converted {converted} S-57 feature classes"}


def geoentity_id(source_cell: str, class_name: str, source_id: str) -> str:
    digest = hashlib.sha1(f"{source_cell}:{class_name}:{source_id}".encode()).hexdigest()[:20]
    return f"geo-noaa-enc-{digest}"

def feature_name(class_name: str, props: dict[str, Any], source_id: str) -> str:
    return str(props.get("OBJNAM") or props.get("NOBJNM") or props.get("INFORM") or f"{class_name} {source_id}")

def point_from_geometry(geometry: dict[str, Any]) -> tuple[float,float] | None:
    if geometry.get("type") == "Point":
        coords=geometry.get("coordinates") or []
        if len(coords)>=2:
            return float(coords[1]),float(coords[0])
    return None

def entity_from_feature(layer: dict[str, Any], source_id: str, props: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    source_cell=str(layer.get("dataset") or layer.get("metadata",{}).get("source_cell") or "ENC")
    class_name=str(layer.get("class_name") or layer.get("name") or "ENC")
    entity_id=geoentity_id(source_cell,class_name,source_id)
    components={
        "aliases":{"name":feature_name(class_name,props,source_id)},
        "ontology":{
            "template":"GEOENTITY",
            "domain":"MARITIME",
            "platform_type":"REFERENCE_FEATURE",
            "specific_type":class_name,
            "geometry_type":geometry.get("type"),
        },
        "geometry":{"geojson":geometry},
        "style":layer.get("style") or style_for(class_name,str(geometry.get("type") or "")),
        "attributes":props,
        "provenance":{
            "source_system":PLUGIN_ID,
            "source_protocol":"S-57",
            "source_dataset":source_cell,
            "source_class":class_name,
            "source_id":source_id,
        },
    }
    point=point_from_geometry(geometry)
    if point:
        components["location"]={"latitude":point[0],"longitude":point[1]}
    return {"entity_id":entity_id,"is_live":True,"components":components,"provenance":components["provenance"]}

async def publish_geoentities(layer: dict[str, Any], collection: dict[str, Any]):
    rows=[]
    for idx,feature in enumerate(collection.get("features") or []):
        geometry=feature.get("geometry")
        if not geometry: continue
        props=feature.get("properties") or {}
        source_id=str(props.get("OBJECTID") or props.get("FID") or props.get("RCID") or props.get("LNAM") or idx)
        rows.append(entity_from_feature(layer,source_id,props,geometry))
    batch_size=200
    for start in range(0,len(rows),batch_size):
        await api("POST","/api/v1/entities/bulk",json=rows[start:start+batch_size])
    return len(rows)

async def cache_features(layer: dict[str, Any], collection: dict[str, Any]):
    assert pool
    count = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            # A locally imported layer is authoritative; remove objects no longer present.
            await conn.execute("DELETE FROM plugin_noaa_enc.features WHERE layer_id=$1", layer["layer_id"])
            for idx, feature in enumerate(collection.get("features") or []):
                geometry = feature.get("geometry")
                if not geometry:
                    continue
                props = feature.get("properties") or {}
                source_id = str(props.get("OBJECTID") or props.get("FID") or props.get("RCID") or props.get("LNAM") or idx)
                try:
                    await conn.execute("""
                        INSERT INTO plugin_noaa_enc.features(layer_id,source_id,properties,geom,observed_at)
                        VALUES($1,$2,$3::jsonb,ST_SetSRID(ST_GeomFromGeoJSON($4),4326),NOW())
                        ON CONFLICT(layer_id,source_id) DO UPDATE SET properties=EXCLUDED.properties,
                            geom=EXCLUDED.geom,observed_at=NOW()
                    """, layer["layer_id"], source_id, json.dumps(props), json.dumps(geometry))
                    count += 1
                except Exception as exc:
                    print(f"[noaa-enc] skipped invalid geometry in {layer['name']}: {exc}")
    published = await publish_geoentities(layer, collection)
    metrics["features_cached"] = int(metrics.get("features_cached", 0)) + count
    metrics["geoentities_published"] = int(metrics.get("geoentities_published", 0)) + published
    return count


async def discover_local_layers(config: dict[str, Any]) -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
    s57_files = sorted(p for p in DATA_DIR.iterdir() if p.is_file() and re.fullmatch(r"\.\d{3}", p.suffix))
    import_reports = []
    if config.get("import_on_startup", True):
        for path in s57_files:
            try:
                report = await asyncio.to_thread(convert_s57, path)
                import_reports.append(report)
                assert pool
                async with pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO plugin_noaa_enc.datasets(filename,source_format,size_bytes,imported_at,status,layer_count,message)
                        VALUES($1,'S-57',$2,NOW(),'READY',$3,$4)
                        ON CONFLICT(filename) DO UPDATE SET size_bytes=EXCLUDED.size_bytes,imported_at=NOW(),status='READY',layer_count=EXCLUDED.layer_count,message=EXCLUDED.message
                    """, path.name, path.stat().st_size, int(report["layers"]), str(report["message"]))
            except Exception as exc:
                metrics["last_error"] = str(exc)
                assert pool
                async with pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO plugin_noaa_enc.datasets(filename,source_format,size_bytes,imported_at,status,layer_count,message)
                        VALUES($1,'S-57',$2,NOW(),'ERROR',0,$3)
                        ON CONFLICT(filename) DO UPDATE SET size_bytes=EXCLUDED.size_bytes,imported_at=NOW(),status='ERROR',layer_count=0,message=EXCLUDED.message
                    """, path.name, path.stat().st_size, str(exc))
                print(f"[noaa-enc] import failed for {path.name}: {exc}")

    geojson_files = sorted(DATA_DIR.glob("*.geojson")) + sorted(CONVERTED_DIR.glob("*/*.geojson"))
    discovered: list[dict[str, Any]] = []
    for path in geojson_files:
        try:
            collection = json.loads(path.read_text(encoding="utf-8"))
            features = collection.get("features") or []
            if collection.get("type") != "FeatureCollection" or not features:
                continue
            geometry_types = {str((f.get("geometry") or {}).get("type") or "") for f in features if f.get("geometry")}
            geometry_type = next(iter(geometry_types)) if len(geometry_types) == 1 else "mixed"
            class_name = path.stem
            source_cell = path.parent.name if path.parent.parent == CONVERTED_DIR else path.name
            layer_id = safe_layer_id(class_name, source_cell)
            display_name = f"{class_name} [{source_cell}]"
            info = {
                "layer_id": layer_id, "remote_id": -1, "name": class_name, "class_name": class_name,
                "display_name": display_name, "dataset": source_cell, "min_zoom": 0, "max_zoom": 24,
                "geometry_type": geometry_type, "local_file": str(path),
                "style": style_for(class_name, geometry_type),
                "metadata": {"source_file": path.name, "source_cell": source_cell, "dataset": source_cell, "class_name": class_name},
            }
            source_mtime_ns = path.stat().st_mtime_ns
            info["metadata"]["source_mtime_ns"] = source_mtime_ns
            assert pool
            async with pool.acquire() as conn:
                existing = await conn.fetchrow("SELECT metadata FROM plugin_noaa_enc.layers WHERE layer_id=$1", layer_id)
                existing_mtime = int((dict(existing["metadata"]) if existing else {}).get("source_mtime_ns", 0)) if existing else 0
                feature_exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM plugin_noaa_enc.features WHERE layer_id=$1)", layer_id)
            published_marker = int((dict(existing["metadata"]) if existing else {}).get("geoentity_publish_version", 0)) if existing else 0
            if existing_mtime != source_mtime_ns or not feature_exists or published_marker < 1:
                await cache_features(info, collection)
            info["metadata"]["geoentity_publish_version"] = 1
            discovered.append(info)
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO plugin_noaa_enc.layers(layer_id,remote_id,name,geometry_type,metadata,discovered_at)
                    VALUES($1,-1,$2,$3,$4::jsonb,NOW())
                    ON CONFLICT(layer_id) DO UPDATE SET name=EXCLUDED.name,geometry_type=EXCLUDED.geometry_type,metadata=EXCLUDED.metadata,discovered_at=NOW()
                """, layer_id, class_name, geometry_type, json.dumps(info["metadata"]))
        except Exception as exc:
            print(f"[noaa-enc] skipped local layer {path}: {exc}")
    metrics["local_files"] = len(geojson_files)
    metrics["s57_cells"] = len(s57_files)
    if import_reports:
        metrics["last_import"] = datetime.now(timezone.utc).isoformat()
    return discovered


async def discover_layers():
    async with _discovery_lock:
        config = await get_config()
        discovered = await discover_local_layers(config)
        disabled_classes = {str(x) for x in config.get("disabled_classes", [])}
        layer_catalog.clear()
        layer_catalog.update({x["layer_id"]: x for x in discovered})
        await register_plugin(config)
        # ENC objects are core GEOENTITY records. The plugin no longer exposes a
        # parallel map-only GIS-feature channel.
        visible = [x for x in discovered if x["class_name"] not in disabled_classes]
        await api("PUT", f"/api/v1/plugins/{PLUGIN_ID}/gis-layers", json={"layers": []})
        metrics["layers_discovered"] = len(discovered)
        metrics["layers_visible"] = len(visible)
        metrics["last_discovery"] = datetime.now(timezone.utc).isoformat()


async def read_cache(layer_id: str, bbox: str) -> dict[str, Any]:
    values = [float(x) for x in bbox.split(",")]
    if len(values) != 4:
        raise ValueError("bbox must be west,south,east,north")
    config = await get_config()
    limit = int(config.get("max_features_per_layer", 10000))
    assert pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT source_id,properties,ST_AsGeoJSON(geom)::json AS geometry
            FROM plugin_noaa_enc.features
            WHERE layer_id=$1 AND geom && ST_MakeEnvelope($2,$3,$4,$5,4326)
            LIMIT $6
        """, layer_id, *values, limit)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": r["source_id"], "properties": dict(r["properties"]), "geometry": r["geometry"]}
        for r in rows
    ]}


async def heartbeat_loop():
    while True:
        try:
            await api("POST", f"/api/v1/plugins/{PLUGIN_ID}/heartbeat", json={
                "status": "RUNNING", "message": f"{metrics['s57_cells']} local ENC cells, {metrics['layers_discovered']} layers", "metrics": metrics,
            })
        except Exception as exc:
            print("[noaa-enc] heartbeat:", exc)
        await asyncio.sleep(10)


async def discovery_loop():
    while True:
        try:
            await discover_layers()
        except Exception as exc:
            metrics["last_error"] = str(exc)
            print("[noaa-enc] discovery:", exc)
        config = await get_config()
        await asyncio.sleep(max(30, int(config.get("refresh_seconds", 120))))


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


app = FastAPI(title="OpenGrid NOAA ENC Plugin", version="0.13.3", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "plugin_id": PLUGIN_ID, "metrics": metrics}


@app.get("/layers")
async def layers():
    return list(layer_catalog.values())


@app.get("/datasets")
async def datasets():
    assert pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM plugin_noaa_enc.datasets ORDER BY imported_at DESC")
    return [dict(row) for row in rows]


@app.post("/import")
async def import_enc(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    if not re.search(r"\.\d{3}$", filename, re.IGNORECASE):
        raise HTTPException(400, "Upload an S-57 ENC base or update file with a .000-.999 extension")
    destination = DATA_DIR / filename
    total = 0
    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > 250 * 1024 * 1024:
                output.close(); destination.unlink(missing_ok=True)
                raise HTTPException(413, "ENC file exceeds 250 MB")
            output.write(chunk)
    try:
        report = await asyncio.to_thread(convert_s57, destination, True)
        await discover_layers()
        return {"status": "imported", "size_bytes": total, **report}
    except Exception as exc:
        metrics["last_error"] = str(exc)
        raise HTTPException(422, f"ENC import failed: {exc}")


@app.delete("/datasets/{filename}")
async def remove_dataset(filename: str):
    safe = Path(filename).name
    source = DATA_DIR / safe
    converted = CONVERTED_DIR / source.stem
    source.unlink(missing_ok=True)
    if converted.exists():
        shutil.rmtree(converted)
    assert pool
    async with pool.acquire() as conn:
        layer_ids = await conn.fetch("SELECT layer_id FROM plugin_noaa_enc.layers WHERE metadata->>'source_cell'=$1", source.stem)
        for row in layer_ids:
            await conn.execute("DELETE FROM plugin_noaa_enc.features WHERE layer_id=$1", row["layer_id"])
        await conn.execute("DELETE FROM plugin_noaa_enc.layers WHERE metadata->>'source_cell'=$1", source.stem)
        await conn.execute("DELETE FROM plugin_noaa_enc.datasets WHERE filename=$1", safe)
    try:
        await api("DELETE", f"/api/v1/entities/by-source/{PLUGIN_ID}", params={"source_dataset": source.stem})
    except Exception as exc:
        print(f"[noaa-enc] core Geo-Entity cleanup failed for {safe}: {exc}")
    await discover_layers()
    return {"status": "removed", "filename": safe}


@app.get("/layers/{layer_id}.geojson")
async def layer_geojson(layer_id: str, bbox: str = Query(...)):
    if layer_id not in layer_catalog:
        raise HTTPException(404, "ENC layer not found")
    return JSONResponse(await read_cache(layer_id, bbox), media_type="application/geo+json", headers={"X-OpenGrid-Source": "local"})
