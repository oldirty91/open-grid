# Task Model

A Task is a durable, deliberate action assigned to a taskable agent.

```json
{
  "description": "Navigate to selected point",
  "specification": {
    "type": "opengrid.tasks.v1.Navigate",
    "objective": {
      "type": "POINT",
      "position": {"latitude": 41.5, "longitude": -71.3}
    },
    "parameters": {"speed_mps": 3.0, "arrival_radius_m": 20}
  },
  "assigned_agent_id": "asset-alpha"
}
```

## Lifecycle

- `STATUS_SENT`
- `STATUS_IN_PROGRESS`
- `STATUS_DONE_OK`
- `STATUS_DONE_NOT_OK`
- `STATUS_CANCELED`

Terminal statuses are not claimable.

## Queues

Each assigned agent has an ordered queue. v0.2 assigns monotonically increasing queue positions. One task executes at a time in the simulator.

## Task Catalog

An Asset advertises currently accepted task definitions through `task_catalog`. The operator UI should prefer these definitions over hard-coded platform checks.
