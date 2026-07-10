# Changelog

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
