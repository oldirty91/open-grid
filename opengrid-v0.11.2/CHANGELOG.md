# OpenGrid v0.11.2

- Fixed API startup failure in NOAA overlay seeding by parameterizing JSON metadata.
- Removed the persistent map-layer control from the main map.
- Added map-overlay display and opacity controls to each MAP_OVERLAY Artifact detail view.
- Map overlay preferences persist in browser storage and update across tabs.
- Web now waits for the API health check before starting, avoiding transient startup 502 responses.

# Changelog

## 0.11.0
- Entity profiles always open in a new tab.
- Profiles list every related Task and direct or Task-derived Artifact.
- Component timestamps and continuously updating age labels.
- Fixed-camera adapter using SDK 0.2.0.
- Snapshot and recording-prototype Artifacts.
- NOAA ENC map-overlay Artifact with layer toggle and opacity.
- Binary Artifact publishing in API and SDK.
- Camera Task definitions and fixed-camera map Entity.

# Changelog

## v0.11.0

### Fixed

- Removed Task-only `claimed_at` and `attempt` fields accidentally inserted into the Entity upsert SQL.
- Restored AIS, ADS-B, simulator, and MAVLink Entity publication.
- Restored MAVLink task claiming, which depends on successful vehicle Entity publication.

## v0.11.0

- Added versioned OpenGrid Python SDK v0.1.0 with retry/backoff, registration, heartbeat, entity, task and artifact helpers.
- Migrated reference AIS and ADS-B request plumbing onto the SDK.
- Added entity profile API and UI with state, capabilities, related tasks, related artifacts and component inspection.
- Added task priority, timeout, attempt limits and dependencies; blocked tasks become claimable when dependencies complete.
- Added fixed-camera and radar symbols to the map icon set.
- Preserved MAVLink behavior without expanding its feature scope.


## v0.9.1

### Fixed

- Corrected JSON-style boolean literals in Python task-definition source.
- `true`, `false`, and `null` are now valid Python `True`, `False`, and `None`.
- API now imports successfully and no longer causes nginx `502 Bad Gateway`.


## v0.9.0

- Added MAVLink mission Artifact workflow
- Added ExecuteMission, PauseMission, ResumeMission and StopMission
- Added derived operational vehicle state and telemetry freshness
- Added AUTOPILOT_VERSION capability capture
- Added structured Task execution metadata
- Added mission progress reporting and mission editor


## v0.8.1

### Fixed

- Task specifications now allow a null objective for objective-free Tasks.
- Arm, Disarm, Takeoff, Land, and ReturnToLaunch can now be submitted from the UI.
- Added a validation regression check for objective-free Tasks.


## v0.8.0

- Arm, Disarm, Takeoff, Land and LaunchAndNavigate Tasks
- COMMAND_ACK and STATUSTEXT handling
- Observed mode, armed-state and altitude verification
- Objective-free vehicle task composer
- Automated launch-to-waypoint workflow
- Normal disarm protection while airborne


## v0.7.4

### Fixed

- Restored the ArduPilot SITL service to the distributed Compose file.
- Changed the default MAVLink adapter connection to TCP
  `ardupilot-sitl:5760`.
- Added the SITL service as a MAVLink adapter dependency.


## v0.7.3

### Fixed

- MAVLink adapter now requests ArduPilot telemetry streams after discovering a
  system heartbeat.
- Explicitly requests GLOBAL_POSITION_INT, ATTITUDE, SYS_STATUS, GPS_RAW_INT,
  and BATTERY_STATUS intervals.
- Retries stream requests while a discovered system has no position.
- Vehicle count now reflects systems with usable position telemetry.

### Diagnostics

- Plugin metrics now include received MAVLink message types and stream-request count.
- MAVLink container output is unbuffered so connection and stream requests are
  visible through `docker compose logs`.


## v0.7.2

### Fixed

- Corrected MAVLink plugin seed configuration SQL.
- Numeric values inside an inline JSON string were incorrectly interpreted by
  SQLAlchemy as bind parameters named `14550` and `30`.
- MAVLink seed JSON is now passed as bound data and cast to JSONB safely.
- Added a schema SQL regression check.


## v0.7.1

### Fixed

- MinIO startup timing can no longer prevent the OpenGrid API from starting.
- Added MinIO health checking and explicit API dependency ordering.
- API and web containers now restart after transient startup failures.
- Artifact operations return HTTP 503 when storage is unavailable rather than
  taking down Entities, Tasks, Plugins, and the map.
- Added a stack diagnostic script.


## v0.7.0

### Added

- MAVLink vehicle-adapter plugin
- UDP, TCP and serial MAVLink connection modes
- MAVLink Asset Entity publication and telemetry components
- Navigate, Loiter and Return-to-Launch task execution
- Upper-left dropdown navigation menu

### Changed

- Switched to a darker OpenFreeMap style.
- Suppressed minor roads, POIs, building detail and road labels for a cleaner
  operational map.

### Safety

- MAVLink control is an initial SITL-focused implementation. Validate behavior
  in simulation before connecting physical vehicles.


## v0.6.0

### Added

- Independent ADS-B reference plugin
- readsb/tar1090 JSON polling
- SBS/BaseStation TCP ingestion
- adsb.lol REST polling
- OpenSky state-vector REST polling
- Generic ADS-B JSON WebSocket ingestion
- ADS-B plugin configuration UI

### Changed

- Default basemap changed to the simpler OpenFreeMap Positron vector style.
- Removed the old raster-map visual filter.


## v0.5.0

### Added

- User-configurable AIS source modes: replay, UDP, TCP and WebSocket
- AISStream.io provider support
- Generic JSON WebSocket support
- Plugin configuration form with live reconnect
- AISStream position and static-data normalization
- Connection/reconnect metrics and logs

### Changed

- AIS plugin configuration is read from the OpenGrid plugin registry.
- Saving configuration causes the source connection to restart without
  rebuilding or restarting the container.


## v0.4.2

### Fixed

- Location-history API now reads directly from authoritative Entity revisions
  and unions the optimized location projection.
- Browser refresh now restores the complete persisted path before appending new
  live positions.
- Frontend API and WebSocket traffic now use same-origin nginx proxy routes,
  eliminating localhost and CORS mismatches on Plugins and Artifacts pages.
- Plugins page now exposes server errors and includes a manual registry refresh.

### Changed

- Nginx proxies `/api/*` to the API container and `/ws/` to the live stream.
- Browser builds no longer hard-code `localhost:8000`.


## v0.4.1

### Fixed

- Added a dedicated database-backed Entity location-sample projection.
- Breadcrumb history now survives browser refresh and service restart.
- Existing Entity revisions are backfilled into the location-sample table.
- The installed Reference AIS plugin is seeded in the plugin registry and is
  visible before its first heartbeat.
- AIS plugin registration now retries instead of exiting after a transient error.
- Plugin and Artifact pages display API errors rather than silently appearing empty.

### Added

- Artifact creation form directly on the Artifacts page.
- Empty-state messaging for Plugins and Artifacts.
- Reference AIS plugin startup log entry.


## v0.4.0

### Added

- Dedicated plugin registry, heartbeat, metrics, configuration and log APIs
- Separate Plugins administration page
- Logical plugin enable and disable controls
- Independent reference AIS Docker plugin
- AIS replay, UDP and TCP input modes
- AIS vessel-type mapping and Track publication
- Minimal MinIO-backed text Artifact creation and download
- Separate Artifacts administration page
- Startup schema creation for existing v0.3 databases

### Architecture

- Plugins remain administrative integrations and are never represented as Entities.
- Plugin health is visible only through the Plugins page and plugin API.


## v0.3.5

### Fixed

- Restored entity icon selection using MapLibre hit testing at the clicked map point.
- Added pointer cursor feedback when hovering over entity symbols.

### Changed

- Breadcrumbs now render as a clean historical line without point markers.
- Declared the current operator UI milestone feature-complete enough to move
  focus back to higher-level platform capabilities.


## v0.3.4

### Fixed

- Replaced all HTML map markers with native MapLibre GeoJSON symbol layers.
  Entity and task symbols now remain tied to latitude/longitude during zoom.
- Rebuilt breadcrumbs as native GeoJSON line and point layers.
- Breadcrumb history merges persisted revisions with live position updates
  instead of allowing periodic database reads to erase live samples.
- Breadcrumbs display for selected Assets and selected Tracks.
- Replaced the task objective marker with a simple native waypoint symbol.

### Changed

- Platform icons are generated as compact filled map images and rendered in a
  MapLibre symbol layer.
- Removed legacy NATO, DOM-marker and crosshair CSS that could conflict with
  MapLibre positioning transforms.


## v0.3.3

### Fixed

- Breadcrumbs now combine persisted revision history with live in-browser
  position accumulation, preventing an empty trail during active operation.
- Breadcrumbs display for both selected Assets and selected Tracks.
- Selected task objective uses a simple fixed-size crosshair.

### Changed

- Removed tactical/NATO framing from all map symbols.
- Replaced symbols with filled, heading-aware platform silhouettes inspired by
  ADS-B and vessel-tracking interfaces.
- Added documented design direction for mission files as Artifacts executed by
  an `ExecuteMission` Task.


## v0.3.2

### Fixed

- Reworked breadcrumb rendering so map sources/layers are installed after MapLibre style load.
- Added breadcrumb point markers and automatic refresh for the selected Asset.
- Replaced the stretched task objective marker with a fixed-size crosshair.

### Changed

- Removed NATO/APP-6-style affiliation frames from map markers.
- Entity markers now use plain platform silhouettes colored by disposition.


## v0.3.1

- Added platform-aware pictograms within NATO-inspired affiliation frames.
- AIS demo tracks now advertise a cargo ship type.
- Completed and canceled tasks are hidden from the active queue but retained in history.
- Added reliable selected-task objective markers.
- Breadcrumbs now appear automatically only for the selected asset.
- Removed breadcrumb and queued-route selectors.


## v0.3.0

### Added

- NATO-inspired semantic symbols
- Location-history endpoint and breadcrumbs
- Generic task composer and confirm-send workflow
- Task cancellation endpoint and simulator cancellation handling
- Selectable task rows with focused map visualization
- Objective markers and selected/queued route styling


## v0.2.2

### Fixed

- Corrected the fusion recency SQL to use `make_interval`, avoiding asyncpg's
  integer-to-text bind error that rolled back every source-track update.
- Existing NATS volumes with the old plural subject configuration are repaired
  in place with `update_stream`.
- Simulator continues running asset and task execution if an individual track
  publication fails.
- Clarified in the UI that Investigate is exposed by selecting a track.


## v0.2.1

### Fixed

- Corrected JetStream subjects from plural (`entities.*`, `tasks.*`) to the
  singular subjects emitted by the API (`entity.*`, `task.*`).
- NATS publication failures no longer turn committed database writes into HTTP 500 responses.
- Simulator retries asset registration and restarts after transient failures.
- Newly created tasks are inserted into the UI immediately, with WebSocket updates remaining authoritative.
- API now waits for the NATS health check during startup.


## v0.2.0

### Added

- Renamed CommonGrid to OpenGrid
- Component PATCH endpoint
- Component revision history and provenance
- WebSocket live update gateway
- Ordered per-agent task queues
- Navigate and Investigate task specifications
- Simulator task claim, execution, progress and completion
- Route visualization
- Capability, limit, equipment and resource examples
- Task Catalog-driven task compatibility
- Expanded OpenAPI metadata and examples
- Project vision, architecture, model and plugin documentation

### Changed

- Fused contacts are now normal `TRACK` entities with fusion components rather than a separate top-level entity template.
- Component source information is recorded without imposing universal exclusive ownership.
- MinIO host S3 API port defaults to 9002 while its container port remains 9000.

### Known issues

- The development simulator and API assume one active API replica.
- Task queue reordering is not yet exposed.
- Artifacts do not yet have a MinIO-backed API.

## 0.11.2
- Generic multi-camera adapter with real configured sources only.
- Camera field-of-view map sectors and live viewing.
- NOAA WMS overlay support and seeded metadata update.
- Automatic source-track aging (ADS-B 5m, AIS 30m, generic 15m).
