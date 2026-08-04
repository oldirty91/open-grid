# MAVLink Operational Maturity

v0.9 focuses on standard MAVLink operation rather than advanced remote autonomy.

## Added

- Derived vehicle operational state
- Telemetry freshness and failsafe visibility
- Capability-driven Task Catalog
- Structured Task execution details
- MAVLink mission JSON Artifacts
- Mission upload, start, pause, resume and stop
- Mission progress from MISSION_CURRENT and MISSION_ITEM_REACHED

## Mission Artifact schema

```json
{"items":[
  {"command":22,"frame":3,"latitude":41.49,"longitude":-71.315,"altitude_m":20},
  {"command":16,"frame":3,"latitude":41.492,"longitude":-71.312,"altitude_m":30},
  {"command":20,"frame":3,"latitude":0,"longitude":0,"altitude_m":0}
]}
```

Commands are standard MAVLink command IDs. The initial editor intentionally
uses a transparent JSON representation before a graphical mission planner is
introduced.
