import asyncio
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import websockets
from pyais import decode

API = os.getenv("OPENGRID_API_URL", "http://localhost:8000")
PLUGIN_ID = os.getenv("PLUGIN_ID", "opengrid.ais.reference")
REPLAY_FILE = os.getenv("AIS_REPLAY_FILE", "/data/sample_ais.jsonl")

DEFAULT_CONFIG = {
    "input_mode": os.getenv("AIS_INPUT_MODE", "replay").lower(),
    "replay_interval_s": float(os.getenv("AIS_REPLAY_INTERVAL_S", "1.5")),
    "udp_host": os.getenv("AIS_UDP_HOST", "0.0.0.0"),
    "udp_port": int(os.getenv("AIS_UDP_PORT", "10110")),
    "tcp_host": os.getenv("AIS_TCP_HOST", "127.0.0.1"),
    "tcp_port": int(os.getenv("AIS_TCP_PORT", "10110")),
    "websocket_provider": "aisstream",
    "websocket_url": "wss://stream.aisstream.io/v0/stream",
    "websocket_api_key": "",
    "bounding_boxes": [[[40.9, -71.8], [41.9, -70.8]]],
    "filter_mmsi": [],
    "filter_message_types": [
        "PositionReport",
        "StandardClassBPositionReport",
        "ExtendedClassBPositionReport",
        "ShipStaticData",
        "StaticDataReport",
    ],
    "generic_subscription_json": {},
}

metrics = {
    "messages_received": 0,
    "entities_active": 0,
    "parse_errors": 0,
    "reconnects": 0,
    "last_message_time": None,
    "current_mode": DEFAULT_CONFIG["input_mode"],
}
active: set[str] = set()
static_cache: dict[str, dict[str, Any]] = {}
SHIP_TYPES = {
    30: "FISHING_VESSEL",
    31: "TOWING_VESSEL",
    36: "SAILING_VESSEL",
    37: "PLEASURE_CRAFT",
    50: "PILOT_VESSEL",
    52: "TUG",
    60: "PASSENGER_SHIP",
    70: "CARGO_SHIP",
    80: "TANKER",
}

async def call(client: httpx.AsyncClient, method: str, path: str, **kwargs):
    response = await client.request(method, f"{API}{path}", **kwargs)
    response.raise_for_status()
    return response

async def register(client: httpx.AsyncClient):
    await call(client, "POST", "/api/v1/plugins/register", json={
        "plugin_id": PLUGIN_ID,
        "name": "AIS",
        "version": "0.2.0",
        "plugin_type": "DATA_SOURCE",
        "protocol": "AIS",
        "capabilities": ["entity.publish", "entity.patch"],
        "configuration_schema": {
            "type": "object",
            "properties": {
                "input_mode": {"type": "string", "enum": ["replay", "udp", "tcp", "websocket"]},
                "udp_host": {"type": "string"},
                "udp_port": {"type": "integer"},
                "tcp_host": {"type": "string"},
                "tcp_port": {"type": "integer"},
                "websocket_provider": {"type": "string", "enum": ["aisstream", "generic"]},
                "websocket_url": {"type": "string"},
                "websocket_api_key": {"type": "string", "secret": True},
                "bounding_boxes": {"type": "array"},
                "filter_mmsi": {"type": "array"},
                "filter_message_types": {"type": "array"},
                "generic_subscription_json": {"type": "object"},
            },
        },
        "configuration": DEFAULT_CONFIG,
    })

async def log(client: httpx.AsyncClient, level: str, message: str, details=None):
    try:
        await call(client, "POST", f"/api/v1/plugins/{PLUGIN_ID}/logs", json={
            "level": level,
            "message": message,
            "details": details or {},
        })
    except Exception:
        pass

async def get_plugin(client: httpx.AsyncClient):
    return (await call(client, "GET", f"/api/v1/plugins/{PLUGIN_ID}")).json()

async def get_config(client: httpx.AsyncClient) -> dict[str, Any]:
    plugin = await get_plugin(client)
    merged = dict(DEFAULT_CONFIG)
    merged.update(plugin.get("configuration") or {})
    return merged

async def heartbeat(client: httpx.AsyncClient):
    while True:
        try:
            plugin = await get_plugin(client)
            await call(client, "POST", f"/api/v1/plugins/{PLUGIN_ID}/heartbeat", json={
                "status": "RUNNING" if plugin.get("enabled", True) else "DISABLED",
                "message": f"AIS input mode: {metrics['current_mode']}",
                "metrics": metrics,
            })
        except Exception as exc:
            print("[ais] heartbeat", exc)
        await asyncio.sleep(5)

def normalize_decoded(data: dict[str, Any]) -> dict[str, Any] | None:
    mmsi = data.get("mmsi") or data.get("UserID") or data.get("MMSI")
    lat = data.get("lat") if data.get("lat") is not None else data.get("Latitude")
    lon = data.get("lon") if data.get("lon") is not None else data.get("Longitude")
    if not mmsi or lat is None or lon is None:
        return None

    mmsi_str = str(mmsi)
    cached = static_cache.get(mmsi_str, {})
    ship_type = data.get("ship_type") or data.get("Type") or cached.get("ship_type")
    course = data.get("course")
    if course is None:
        course = data.get("Cog")
    if course is None:
        course = data.get("heading")
    if course is None:
        course = data.get("TrueHeading")
    speed = data.get("speed")
    if speed is None:
        speed = data.get("Sog")
    name = data.get("shipname") or data.get("Name") or cached.get("name")
    callsign = data.get("callsign") or data.get("CallSign") or cached.get("callsign")
    destination = data.get("destination") or data.get("Destination") or cached.get("destination")

    course = float(course or 0)
    speed_knots = float(speed or 0)
    return {
        "entity_id": f"ais-{mmsi_str}",
        "components": {
            "aliases": {"name": name or f"MMSI {mmsi_str}", "callsign": callsign},
            "ontology": {
                "template": "TRACK",
                "domain": "MARITIME",
                "track_type": "SOURCE",
                "specific_type": SHIP_TYPES.get(ship_type, "VESSEL"),
            },
            "location": {
                "latitude": float(lat),
                "longitude": float(lon),
                "heading_degrees": course,
                "course_degrees": course,
                "speed_mps": speed_knots * 0.514444,
            },
            "ais": {
                "mmsi": int(mmsi),
                "ship_type": ship_type,
                "navigation_status": data.get("status") or data.get("NavigationalStatus"),
                "destination": destination,
            },
            "status": {
                "state": "LIVE",
                "last_observed_time": datetime.now(timezone.utc).isoformat(),
            },
            "provenance": {
                "source_system": PLUGIN_ID,
                "source_protocol": "AIS",
                "source_id": mmsi_str,
            },
        },
        "provenance": {
            "source_system": PLUGIN_ID,
            "source_protocol": "AIS",
        },
    }

def normalize_aisstream(message: dict[str, Any]) -> dict[str, Any] | None:
    if "error" in message:
        raise RuntimeError(message["error"])
    message_type = message.get("MessageType")
    body = (message.get("Message") or {}).get(message_type, {})
    metadata = message.get("MetaData") or message.get("Metadata") or {}
    mmsi = body.get("UserID") or metadata.get("MMSI")
    if not mmsi:
        return None
    mmsi_str = str(mmsi)

    if message_type in {"ShipStaticData", "StaticDataReport"}:
        static_cache[mmsi_str] = {
            "name": body.get("Name") or metadata.get("ShipName"),
            "callsign": body.get("CallSign"),
            "destination": body.get("Destination"),
            "ship_type": body.get("Type"),
        }
        return None

    data = dict(body)
    data["MMSI"] = mmsi
    data["Name"] = metadata.get("ShipName") or data.get("Name")
    if data.get("Latitude") is None:
        data["Latitude"] = metadata.get("latitude") or metadata.get("Latitude")
    if data.get("Longitude") is None:
        data["Longitude"] = metadata.get("longitude") or metadata.get("Longitude")
    return normalize_decoded(data)

async def publish(client: httpx.AsyncClient, entity: dict[str, Any] | None):
    if not entity:
        return
    await call(client, "PUT", f"/api/v1/entities/{entity['entity_id']}", json=entity)
    active.add(entity["entity_id"])
    metrics["messages_received"] += 1
    metrics["entities_active"] = len(active)
    metrics["last_message_time"] = datetime.now(timezone.utc).isoformat()

async def replay_source(config: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    records = [json.loads(line) for line in Path(REPLAY_FILE).read_text().splitlines() if line.strip()]
    index = 0
    while True:
        record = dict(records[index % len(records)])
        loop = index // len(records)
        record["lat"] = float(record["lat"]) + 0.00015 * loop
        record["lon"] = float(record["lon"]) + 0.00010 * loop
        yield record
        index += 1
        await asyncio.sleep(float(config.get("replay_interval_s", 1.5)))

async def udp_source(config: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((str(config.get("udp_host", "0.0.0.0")), int(config.get("udp_port", 10110))))
    sock.setblocking(False)
    try:
        while True:
            payload, _ = await loop.sock_recvfrom(sock, 8192)
            for line in payload.decode(errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    yield decode(line.strip()).asdict()
                except Exception:
                    metrics["parse_errors"] += 1
    finally:
        sock.close()

async def tcp_source(config: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    reader, writer = await asyncio.open_connection(
        str(config.get("tcp_host", "127.0.0.1")),
        int(config.get("tcp_port", 10110)),
    )
    try:
        while line := await reader.readline():
            try:
                yield decode(line.decode(errors="ignore").strip()).asdict()
            except Exception:
                metrics["parse_errors"] += 1
    finally:
        writer.close()
        await writer.wait_closed()

async def websocket_source(config: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    url = str(config.get("websocket_url") or "wss://stream.aisstream.io/v0/stream")
    provider = str(config.get("websocket_provider") or "aisstream").lower()
    async with websockets.connect(url, ping_interval=20, ping_timeout=20, max_queue=2048) as websocket:
        if provider == "aisstream":
            api_key = str(config.get("websocket_api_key") or "")
            if not api_key:
                raise RuntimeError("AISStream API key is required")
            subscription = {
                "APIKey": api_key,
                "BoundingBoxes": config.get("bounding_boxes") or [[[-90, -180], [90, 180]]],
            }
            if config.get("filter_mmsi"):
                subscription["FiltersShipMMSI"] = config["filter_mmsi"]
            if config.get("filter_message_types"):
                subscription["FilterMessageTypes"] = config["filter_message_types"]
            await websocket.send(json.dumps(subscription))
        else:
            subscription = config.get("generic_subscription_json") or {}
            if subscription:
                await websocket.send(json.dumps(subscription))

        async for raw in websocket:
            message = json.loads(raw)
            if provider == "aisstream":
                entity = normalize_aisstream(message)
                if entity:
                    yield entity
            else:
                # Generic WebSocket accepts either AISStream-style JSON,
                # decoded AIS dictionaries, or raw NMEA in a JSON/string message.
                if isinstance(message, dict) and message.get("MessageType"):
                    entity = normalize_aisstream(message)
                    if entity:
                        yield entity
                elif isinstance(message, dict):
                    yield message

def config_signature(config: dict[str, Any]) -> str:
    relevant = {
        key: config.get(key)
        for key in [
            "input_mode", "replay_interval_s", "udp_host", "udp_port",
            "tcp_host", "tcp_port", "websocket_provider", "websocket_url",
            "websocket_api_key", "bounding_boxes", "filter_mmsi",
            "filter_message_types", "generic_subscription_json",
        ]
    }
    return json.dumps(relevant, sort_keys=True)

async def run_source(client: httpx.AsyncClient, config: dict[str, Any]):
    mode = str(config.get("input_mode", "replay")).lower()
    metrics["current_mode"] = mode
    await log(client, "INFO", "AIS source starting", {"mode": mode})

    if mode == "replay":
        source = replay_source(config)
    elif mode == "udp":
        source = udp_source(config)
    elif mode == "tcp":
        source = tcp_source(config)
    elif mode == "websocket":
        source = websocket_source(config)
    else:
        raise RuntimeError(f"Unsupported AIS input mode: {mode}")

    start_signature = config_signature(config)
    async for item in source:
        plugin = await get_plugin(client)
        if not plugin.get("enabled", True):
            await asyncio.sleep(1)
            continue
        current = await get_config(client)
        if config_signature(current) != start_signature:
            await log(client, "INFO", "AIS configuration changed; reconnecting")
            return

        if mode == "websocket" and item.get("entity_id"):
            entity = item
        else:
            entity = normalize_decoded(item)
        await publish(client, entity)

async def main():
    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            try:
                if (await client.get(f"{API}/health")).is_success:
                    break
            except Exception:
                pass
            await asyncio.sleep(2)

        while True:
            try:
                await register(client)
                break
            except Exception as exc:
                print("[ais] register", exc)
                await asyncio.sleep(2)

        asyncio.create_task(heartbeat(client))

        while True:
            try:
                plugin = await get_plugin(client)
                if not plugin.get("enabled", True):
                    await asyncio.sleep(2)
                    continue
                config = await get_config(client)
                await run_source(client, config)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                metrics["parse_errors"] += 1
                metrics["reconnects"] += 1
                print("[ais] source", exc)
                await log(client, "ERROR", "AIS source connection failed", {"error": str(exc)})
                await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
