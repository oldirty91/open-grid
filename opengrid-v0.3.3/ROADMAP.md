# Roadmap

## v0.3 — Artifacts and planning

- MinIO-backed Artifact upload, download, metadata and checksums
- Artifact relationships to Entities and Tasks
- Survey, loiter and patrol task specifications
- Route and polygon drawing tools
- Task queue reorder, pause and cancel
- Timeline and historical playback foundation

## v0.4 — Plugin SDK

- Formal plugin manifest
- Plugin registration and heartbeat
- Durable entity publication helpers
- Durable task subscription and claim
- Artifact client
- Reference plugins: simulator, AIS, MAVLink
- Plugin conformance tests

## v0.5 — Security and collaboration

- OpenID Connect
- Service identities
- Operator roles
- Task approval policies
- Multi-user activity and audit views

## Later

- ROS 2, MOOS, DDS, CoT, ADS-B, radar and weather plugins
- Offline/edge synchronization
- Probabilistic multi-source fusion
- AI observation, classification and task-recommendation plugins
- Multi-agent planning
- 3D operational view

## Architectural work to preserve

- Known component schema registry while retaining unknown components
- Source authority and conflict-resolution policies
- Revision retention and telemetry compaction
- Spatially filtered subscriptions
- Optimistic concurrency and source sequence handling
- Task queue reordering and dependency semantics
- Multi-API-instance WebSocket fanout


## Mission-file execution direction

- Store pre-authored mission files as Artifacts.
- Add an `ExecuteMission` Task definition that references an Artifact.
- Allow plugins to declare supported mission MIME types and schema versions.
- Preserve execution state as Task history and outputs as Artifacts.
