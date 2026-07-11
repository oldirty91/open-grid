# Changelog

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
