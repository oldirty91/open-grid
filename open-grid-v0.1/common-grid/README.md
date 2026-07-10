# CommonGrid v0.1

A clean-sheet common operating picture and autonomous-asset orchestration platform.

## Included

- Component-based entities
- Current state plus immutable entity events
- Tasks and task status
- Bare-bones correlation/fusion from the first release
- PostgreSQL/PostGIS
- NATS JetStream
- React + MapLibre UI
- Docker Compose
- Simulator publishing two assets and two correlated source tracks

## Run

```bash
docker compose up --build
```

Open:

- UI: http://localhost:8080
- API docs: http://localhost:8000/docs
- NATS monitor: http://localhost:8222
- MinIO console: http://localhost:9001

## Fusion v0

When a live source `TRACK` arrives, the API finds the nearest recently updated track from a different source system inside a 250 m gate. It creates or updates a deterministic `FUSED_TRACK`, averages the two positions, records a confidence score, and preserves `derived_from` links to the source tracks.

This is intentionally simple. The next fusion iteration should add covariance, course/speed gating, source reliability, association persistence, split/merge handling, and operator overrides.


## Future notes

he first fusion upgrade should add:

Position covariance
Velocity and heading gates
Source reliability
Persistent association identity
Track coast and expiry
Association split and merge handling
Manual correlate/decorrelate controls
Confidence history
Multiple-source fusion beyond pairs


