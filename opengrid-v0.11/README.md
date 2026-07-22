# OpenGrid v0.11.0

OpenGrid is an open operational world model for autonomous systems.

Its public domain model stays intentionally small:

- **Entities** — what exists
- **Tasks** — deliberate work assigned to taskable agents
- **Artifacts** — persistent binary or document-based products

Everything else supports those three concepts.

## What v0.2 demonstrates

- Component-based, non-rigid entities
- Current entity projections in PostgreSQL/PostGIS
- Complete component revision history
- Basic source-track correlation and fused track projection
- Live entity and task updates over WebSocket
- Ordered task queues per asset
- `Navigate` and `Investigate` task specifications
- Simulator execution of queued tasks
- Capability, limit, equipment and resource components
- Lattice-inspired Task Catalog behavior
- Improved interactive OpenAPI documentation

## Run

```bash
docker compose up --build
```

Open:

- UI: http://localhost:8080
- API documentation: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- NATS monitor: http://localhost:8222
- MinIO console: http://localhost:9001
- MinIO S3 API from the host: http://localhost:9002

Inside Docker, services still reach MinIO at `http://minio:9000`.

## Clean start

v0.2 uses a new OpenGrid database and volume name. To reset all development data:

```bash
docker compose down -v
docker compose up --build
```

## Try the operator loop

1. Select `ALPHA`.
2. Right-click the map.
3. Send a Navigate task.
4. Watch the route and task progress update live.
5. Select a source or fused track.
6. Press **Investigate with ALPHA**.
7. Add more tasks while one is running; they remain ordered in ALPHA's queue.

## Entity storage

`entities_current` is the latest materialized world state.

`entity_revisions` stores every accepted full or component-level revision. A battery, location, health or capability timeline is therefore preserved without introducing another public domain concept.

Known components may be validated by future schema definitions. Unknown extension components are retained unchanged.

## Capabilities and platform identity

An asset can retain a lightweight identity such as `USV`, `AUV`, `UAV` or `UGV`, while behavior is driven mainly by current capabilities and its Task Catalog.

The included simulated assets advertise:

- Platform identity
- Physical limits
- Installed equipment
- Consumable resources
- Currently available capabilities
- Currently accepted task definitions

A capability being advertised as available means the responsible plugin believes it is usable now.

## API examples

Patch one component without replacing the rest of the entity:

```bash
curl -X PATCH http://localhost:8000/api/v1/entities/asset-alpha/components/operator_notes \
  -H 'Content-Type: application/json' \
  -d '{
    "value": {"text": "Ready for sortie"},
    "provenance": {"source_system": "operator-ui"}
  }'
```

Queue a Navigate task:

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "description": "Navigate ALPHA to selected point",
    "specification": {
      "type": "opengrid.tasks.v1.Navigate",
      "objective": {
        "type": "POINT",
        "position": {"latitude": 41.502, "longitude": -71.301}
      },
      "parameters": {"speed_mps": 3.0, "arrival_radius_m": 20}
    },
    "assigned_agent_id": "asset-alpha",
    "created_by": "operator"
  }'
```

## Documentation

- [Vision](docs/VISION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Entity Model](docs/ENTITY_MODEL.md)
- [Task Model](docs/TASK_MODEL.md)
- [Plugin Architecture](docs/PLUGINS.md)
- [Lattice Concept Mapping](docs/LATTICE_CONCEPTS.md)
- [Roadmap](ROADMAP.md)
- [Changelog](CHANGELOG.md)

## Important limitations

- Fusion is intentionally basic nearest-neighbor association.
- The simulator claims tasks by polling; a future plugin SDK will use durable streaming.
- WebSocket subscriptions are currently broad rather than spatially filtered.
- Artifacts are a documented core concept, but MinIO-backed upload/download APIs are scheduled next.
- Authentication and authorization are not implemented.
- Component schemas are not yet dynamically registered.
- Task queue order is currently assigned at creation and is not yet reorderable in the UI.
- High-rate telemetry retention and compaction policies are not yet implemented.


## v0.2.1 recovery note

The v0.2 event stream used singular API subjects but configured plural JetStream
subjects. Database writes committed successfully, but the subsequent publish
raised an HTTP 500. This could leave ALPHA in the database while terminating the
simulator before BRAVO was registered, and tasks would only appear after refresh.

v0.2.1 corrects the subject names and treats NATS delivery as best-effort relative
to the authoritative PostgreSQL write.


## v0.2.2 recovery note

v0.2.1 still had an asyncpg typing issue in the fusion query. PostgreSQL inferred
the interval concatenation argument as text while the API supplied an integer.
The resulting transaction rollback prevented all source tracks from being
stored, so the track-selected Investigate action never appeared.

v0.2.2 uses `make_interval(secs => :max_age)` and repairs previously persisted
JetStream subject configuration automatically.


## v0.3 operator workflow

- NATO-inspired semantic symbols
- Entity breadcrumbs from stored location revisions
- Generic Task Catalog-driven task composer
- Review and Confirm Send
- Cancel queued or active tasks with confirmation
- Select a task to focus its route and objective on the map
- Layer controls for breadcrumbs and queued routes

The symbols are NATO-inspired and are not presented as a complete MIL-STD-2525 implementation.


## v0.3.1
Platform-aware symbols, active-only task queue, reliable task objective marker, and automatic selected-asset breadcrumbs.


## v0.3.2 map marker fixes

- Breadcrumbs are automatically shown only for the selected Asset.
- Breadcrumb sources and layers are created after the MapLibre style is ready.
- Task objectives use a fixed-size crosshair.
- Map entities use plain platform silhouettes instead of NATO-style frames.


## v0.3.3 map updates

- Selected Assets and Tracks show breadcrumbs automatically.
- Breadcrumbs combine database history with live position updates.
- Platform markers are simple filled silhouettes rather than NATO-style frames.
- Aircraft and vessel icons rotate using entity heading.
- Task objectives use a simple crosshair.

## Missions as Artifacts

The current design direction is to store pre-authored mission files as
Artifacts. An Asset can advertise an `ExecuteMission` Task, and that Task
references the mission Artifact to run. See `docs/MISSIONS_AS_ARTIFACTS.md`.


## v0.3.4 geospatial marker correction

Entity icons, breadcrumbs and task waypoints are now rendered as native
MapLibre GeoJSON layers. They are no longer HTML elements positioned over the
map, eliminating the apparent southward movement and scaling distortion during
zoom.

A breadcrumb is the historical latitude/longitude path of the selected Entity.
OpenGrid merges stored location revisions with live incoming positions and
renders both a trail line and individual historical points.

A selected Task objective is rendered as a simple circular waypoint.


## v0.3.5 interaction cleanup

- Entity symbols are clickable again and select the corresponding Entity.
- Breadcrumbs are shown as a historical track line only.
- The v0.3 operator-map milestone is now considered stable enough to pause
  visual refinement and return to core platform development.


## v0.4 Plugin Foundation

- Dedicated plugin registry and administrative API
- Separate Plugins page
- Plugin heartbeat, metrics, configuration and logs
- Logical enable/disable controls
- Independent reference AIS Docker plugin
- Replay, UDP and TCP AIS input modes
- Vessel Track Entity publication
- Minimal MinIO-backed text Artifact service
- Plugin health remains outside the Entity model

The reference AIS plugin runs in replay mode by default and publishes three moving vessel Tracks.


## v0.4.1 persistence and administration fixes

Entity tracks are now persisted in the dedicated `entity_location_samples`
table. The table is an internal projection of Entity revision history and does
not add a new OpenGrid core concept.

On startup, OpenGrid backfills this projection from existing Entity revisions.
Breadcrumbs therefore survive page refreshes.

The Reference AIS plugin is also seeded as an installed plugin record. It
appears as OFFLINE until its container registers and begins heartbeats.

The Artifacts page now includes a direct form for creating the first text
Artifact instead of requiring a plugin to be selected first.


## v0.4.2 history and administration networking

The Entity revision table is the authoritative historical record. The
location-history endpoint now reads those revisions directly and combines them
with the optimized location projection. Refreshing the UI should therefore
restore the entire available historical path.

The web container now proxies API and WebSocket traffic to the backend. Browser
pages use same-origin `/api` and `/ws` routes rather than hard-coded localhost
addresses. This specifically addresses Plugins and Artifacts pages showing
`Failed to fetch` while the map continued to function.


## v0.5 AIS connection modes

The AIS plugin can now be configured from the Plugins page for:

- replay data,
- AIS NMEA received on a UDP listener,
- AIS NMEA read from a TCP server,
- AIS JSON received over WebSocket,
- AISStream.io using its authenticated subscription format.

Changing the saved configuration causes the plugin to close its current source
and reconnect with the new settings.

For AISStream.io, configure a WSS URL, API key, bounding boxes and optional MMSI
or message-type filters. The connection is made by the backend plugin container,
not the browser.


## v0.6 ADS-B and simplified basemap

The ADS-B reference plugin supports replay, local readsb/tar1090 JSON, SBS TCP, adsb.lol REST, OpenSky REST, and generic JSON WebSocket sources.

The default map uses the OpenFreeMap Positron vector style for a cleaner, less cluttered operational background.


## v0.7 MAVLink control foundation

- Upper-left dropdown navigation menu
- Darker, simplified vector basemap
- Independent MAVLink vehicle-adapter plugin
- UDP listener, UDP remote, TCP and serial connection modes
- MAVLink heartbeat discovery and Asset Entity creation
- Position, attitude, battery, GPS, mode and armed-state telemetry
- Navigate, Loiter and Return-to-Launch task advertisement and execution
- Initial ArduPilot/PX4 SITL-oriented workflow

The initial control implementation is intentionally narrow. Test with SITL
before connecting physical aircraft.


## v0.7.1 startup reliability

A `502 Bad Gateway` from the web container means nginx is running but the API
container is not reachable. v0.7.1 prevents optional Artifact storage startup
from taking down the entire API and adds dependency health checks.

For diagnostics:

```bash
sh scripts/diagnose.sh
```


## v0.7.2 API startup correction

v0.7.0 and v0.7.1 contained an invalid MAVLink plugin seed query. SQLAlchemy
interpreted the JSON fragments `:14550` and `:30` as named bind parameters,
causing API startup to fail before nginx could reach it.

v0.7.2 passes the plugin configuration as a normal bound string and casts it to
PostgreSQL JSONB.


## v0.7.3 ArduPilot telemetry streaming

ArduPilot SITL can accept the TCP connection and send heartbeats without
automatically streaming position data. The adapter now requests the full data
stream and specific message intervals after each discovered heartbeat.

The MAVLink plugin metrics include a `message_types` object. A working
ArduCopter connection should begin showing `GLOBAL_POSITION_INT`, `ATTITUDE`,
`SYS_STATUS`, and related messages before an Asset appears.


## Included ArduPilot SITL

The default Compose stack includes `radarku/ardupilot-sitl`. The case-sensitive
vehicle setting is `ArduCopter`, and the MAVLink adapter connects over TCP to
`ardupilot-sitl:5760`.


## v0.8 UAV launch and recovery

Adds Arm, Disarm, Takeoff, Land, Navigate, Loiter, RTL and an automated
LaunchAndNavigate Task. The automated task enters GUIDED, arms, takes off, and
navigates without requiring an external GCS. Commands wait for COMMAND_ACK and
verify observed vehicle state. Normal disarm is blocked while airborne.


## v0.8.1 objective-free Tasks

Tasks such as Arm, Disarm, Takeoff, Land, and ReturnToLaunch do not require a
map or Entity objective. The API model now accepts `objective: null` for these
Task types.


## v0.9 MAVLink operational maturity

- Vehicle state derived from live MAVLink telemetry
- Capability-driven task advertisement
- Structured task execution details
- Mission Artifacts and MAVLink Mission Protocol upload
- Execute, pause, resume and stop mission tasks
- Mission progress reporting


## v0.9.1 startup fix

The v0.9 task definitions accidentally used JSON boolean syntax inside Python.
This prevented the API module from importing. v0.9.1 corrects those literals.


## v0.10 highlights
- Versioned Python adapter SDK v0.1.0
- AIS and ADS-B HTTP plumbing migrated to the SDK
- Entity profile pages with related tasks and artifacts
- Task priority, dependencies, timeout and retry metadata
- Fixed camera and radar map symbols
- Artifact relationship workflow strengthened


## v0.11.0 hotfix

Corrects the Entity upsert regression that caused HTTP 500 responses for all live adapters.


## v0.11 sensor and map-overlay demo

The bundled `camera-plugin` publishes `sensor-ridot-south-pier`. Select it on the map and open its profile in a new tab. Create `CaptureSnapshot` or `RecordForDuration` Tasks from the API/task composer. Generated media appears under Artifacts and on the Entity profile. The NOAA ENC Artifact is loaded as a toggleable map layer. All NOAA display data is for situational awareness and is not certified for navigation.
