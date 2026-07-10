import asyncio
import math
import os
from typing import Any
import httpx

API = os.getenv("API_URL", "http://localhost:8000")
PLUGIN_ID = "opengrid-simulator-v0.2"

ASSETS: dict[str, dict[str, float]] = {
    "asset-alpha": {"lat": 41.490, "lon": -71.315, "speed": 0.0, "heading": 0.0},
    "asset-bravo": {"lat": 41.505, "lon": -71.295, "speed": 0.0, "heading": 180.0},
}
ACTIVE: dict[str, dict[str, Any]] = {}

def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.atan2(math.sqrt(a), math.sqrt(1-a))

def move_toward(asset, target_lat, target_lon, speed_mps, dt):
    distance = haversine_m(asset["lat"], asset["lon"], target_lat, target_lon)
    if distance < 0.01:
        return distance
    fraction = min(1.0, speed_mps * dt / distance)
    asset["lat"] += (target_lat - asset["lat"]) * fraction
    asset["lon"] += (target_lon - asset["lon"]) * fraction
    y = math.sin(math.radians(target_lon - asset["lon"])) * math.cos(math.radians(target_lat))
    x = (
        math.cos(math.radians(asset["lat"])) * math.sin(math.radians(target_lat))
        - math.sin(math.radians(asset["lat"])) * math.cos(math.radians(target_lat))
          * math.cos(math.radians(target_lon - asset["lon"]))
    )
    asset["heading"] = (math.degrees(math.atan2(y, x)) + 360) % 360
    asset["speed"] = speed_mps
    return distance

async def patch(client, entity_id, component_name, value):
    response = await client.patch(
        f"{API}/api/v1/entities/{entity_id}/components/{component_name}",
        json={
            "value": value,
            "provenance": {"source_system": PLUGIN_ID, "plugin_id": PLUGIN_ID},
        },
    )
    response.raise_for_status()

async def put_asset(client, entity_id, name, platform_type, lat, lon):
    side_scan = entity_id == "asset-alpha"
    components = {
        "aliases": {"name": name, "callsign": name},
        "ontology": {
            "template": "ASSET",
            "domain": "MARITIME",
            "platform_type": platform_type,
        },
        "location": {
            "latitude": lat,
            "longitude": lon,
            "heading_degrees": 0,
            "speed_mps": 0,
        },
        "health": {"connection": "ONLINE", "overall": "NOMINAL"},
        "limits": {
            "speed": {"minimum_mps": 0, "maximum_mps": 8},
            "depth": {"minimum_m": 0, "maximum_m": 0},
            "turn_radius_m": 8,
        },
        "equipment": {
            "installed": (
                [{"equipment_id": "sss-01", "type": "SIDE_SCAN_SONAR"}]
                if side_scan else []
            )
        },
        "resources": {
            "battery": {"remaining_percent": 92 if side_scan else 84},
            "consumables": (
                [{
                    "resource_id": "red-flares",
                    "type": "SIGNAL_FLARE_RED",
                    "remaining": 3,
                    "capacity": 6,
                    "unit": "COUNT",
                }]
                if side_scan else []
            ),
        },
        "capabilities": {
            "available": [
                {"name": "navigate"},
                {"name": "investigate"},
                *(
                    [{
                        "name": "side_scan_sonar",
                        "constraints": {
                            "recommended_speed_mps": {"minimum": 1, "maximum": 3}
                        },
                    },
                    {
                        "name": "launch_flare",
                        "constraints": {"remaining_uses": 3},
                    }]
                    if side_scan else []
                ),
            ]
        },
        "task_catalog": {
            "definitions": [
                {"type": "opengrid.tasks.v1.Navigate", "version": "1.0.0"},
                {"type": "opengrid.tasks.v1.Investigate", "version": "1.0.0"},
            ]
        },
        "provenance": {"source_system": PLUGIN_ID},
    }
    response = await client.put(
        f"{API}/api/v1/entities/{entity_id}",
        json={
            "entity_id": entity_id,
            "components": components,
            "provenance": {"source_system": PLUGIN_ID, "plugin_id": PLUGIN_ID},
        },
    )
    response.raise_for_status()

async def put_track(client, entity_id, name, lat, lon, source):
    response = await client.put(
        f"{API}/api/v1/entities/{entity_id}",
        json={
            "entity_id": entity_id,
            "components": {
                "aliases": {"name": name},
                "ontology": {
                    "template": "TRACK",
                    "domain": "MARITIME",
                    "track_type": "SOURCE",
                },
                "location": {
                    "latitude": lat,
                    "longitude": lon,
                    "heading_degrees": 64,
                    "speed_mps": 4,
                },
                "mil_view": {"disposition": "UNKNOWN"},
                "provenance": {"source_system": source},
            },
            "provenance": {"source_system": source},
        },
    )
    response.raise_for_status()

async def resolve_objective(client, task):
    specification = task["specification"]
    objective = specification["objective"]
    if objective["type"] == "POINT":
        position = objective["position"]
        return float(position["latitude"]), float(position["longitude"])
    if objective["type"] == "ENTITY":
        response = await client.get(f"{API}/api/v1/entities/{objective['entity_id']}")
        response.raise_for_status()
        entity = response.json()
        location = entity["components"]["location"]
        return float(location["latitude"]), float(location["longitude"])
    raise ValueError("Unsupported objective")

async def claim(client, asset_id):
    response = await client.post(
        f"{API}/api/v1/tasks/claim-next/{asset_id}",
        json={"plugin_id": PLUGIN_ID},
    )
    response.raise_for_status()
    return response.json()

async def update_task(client, task_id, status, progress, message):
    response = await client.post(
        f"{API}/api/v1/tasks/{task_id}/status",
        json={
            "status": status,
            "progress": progress,
            "message": message,
            "actor_id": PLUGIN_ID,
        },
    )
    response.raise_for_status()

async def main():
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            try:
                if (await client.get(f"{API}/health")).status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(2)

        while True:
            try:
                await put_asset(client, "asset-alpha", "ALPHA", "USV", 41.490, -71.315)
                await put_asset(client, "asset-bravo", "BRAVO", "USV", 41.505, -71.295)
                break
            except Exception as exc:
                print(f"[simulator] asset registration failed; retrying: {exc}")
                await asyncio.sleep(2)

        t = 0.0
        dt = 1.0
        while True:
            base_lat = 41.498 + 0.004 * math.sin(t / 18)
            base_lon = -71.305 + 0.005 * math.cos(t / 18)
            try:
                await put_track(
                    client, "radar-track-77", "RADAR 77",
                    base_lat + 0.00020, base_lon - 0.00015, "radar-a"
                )
                await put_track(
                    client, "ais-track-123456789", "MMSI 123456789",
                    base_lat - 0.00015, base_lon + 0.00012, "ais-b"
                )
            except Exception as exc:
                print(f"[simulator] track publication failed; continuing: {exc}")

            for asset_id, asset in ASSETS.items():
                if asset_id not in ACTIVE:
                    task = await claim(client, asset_id)
                    if task:
                        target = await resolve_objective(client, task)
                        start_distance = max(
                            haversine_m(asset["lat"], asset["lon"], *target), 1.0
                        )
                        ACTIVE[asset_id] = {
                            "task": task,
                            "target": target,
                            "start_distance": start_distance,
                        }

                if asset_id in ACTIVE:
                    active = ACTIVE[asset_id]
                    task = active["task"]
                    params = task["specification"].get("parameters") or {}
                    speed = min(float(params.get("speed_mps", 3.0)), 8.0)
                    task_type = task["specification"]["type"]
                    arrival = float(
                        params.get(
                            "arrival_radius_m",
                            params.get("standoff_m", 50 if task_type.endswith("Investigate") else 20),
                        )
                    )
                    target = active["target"]
                    distance = move_toward(asset, *target, speed, dt)
                    progress = max(0.0, min(0.99, 1 - distance / active["start_distance"]))
                    if distance <= arrival:
                        asset["speed"] = 0
                        await update_task(
                            client, task["task_id"], "STATUS_DONE_OK", 1.0,
                            f"Completed within {arrival:.0f} m",
                        )
                        del ACTIVE[asset_id]
                    else:
                        await update_task(
                            client, task["task_id"], "STATUS_IN_PROGRESS",
                            progress, f"{distance:.0f} m remaining",
                        )
                else:
                    asset["speed"] = 0

                await patch(
                    client,
                    asset_id,
                    "location",
                    {
                        "latitude": asset["lat"],
                        "longitude": asset["lon"],
                        "heading_degrees": asset["heading"],
                        "speed_mps": asset["speed"],
                    },
                )

            t += dt
            await asyncio.sleep(dt)

if __name__ == "__main__":
    asyncio.run(main())
