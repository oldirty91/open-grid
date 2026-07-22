# Architecture

```text
External systems and robots
  MAVLink | ROS 2 | MOOS | AIS | Radar | Weather | AI
                         |
                       Plugins
                         |
              Entity / Task / Artifact APIs
                         |
          +--------------+---------------+
          |                              |
     PostgreSQL/PostGIS              NATS JetStream
 current projections + history       internal distribution
          |
       Web API
          |
     WebSocket + REST
          |
      Operator UI
```

## Current projection and history

OpenGrid stores fast current-state projections and append-only revisions.

- `entities_current`: latest merged entity
- `entity_revisions`: full and component-level entity updates
- `tasks`: latest task state and queue position
- `task_revisions`: task lifecycle history
- `fusion_associations`: source-to-fused-track association records

This is not a claim that Events are a fourth core concept. Revisions are an implementation mechanism that preserves history, supports audit and feeds live subscriptions.

## Service boundaries

v0.2 remains a modular monolith for the backend. Domain modules can later be extracted only when independent scaling or deployment requires it.

## Fusion

Source tracks remain visible. The fusion service creates a normal `TRACK` entity with:

- `ontology.track_type = FUSED`
- `fusion`
- `relationships.derived_from`
- fusion provenance

## Task queue

Tasks are ordered per assigned agent. Only one task is claimed by a simulated agent at a time. Additional tasks remain `STATUS_SENT` until earlier work reaches a terminal state.
