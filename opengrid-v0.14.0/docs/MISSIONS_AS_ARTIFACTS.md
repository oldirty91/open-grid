
# Missions as Artifacts

A pre-authored mission is best represented as an Artifact rather than a new
top-level OpenGrid concept.

Example flow:

1. Upload a mission file as an Artifact.
2. Relate the Artifact to compatible Assets or mission-planning tools.
3. A taskable Asset advertises `opengrid.tasks.v1.ExecuteMission`.
4. The operator creates one Task whose parameter references the mission Artifact.
5. The responsible plugin downloads, validates and executes the file.
6. Execution status remains the status of the Task.
7. Logs, imagery and reports produced by execution become additional Artifacts.

Example Task specification:

```json
{
  "type": "opengrid.tasks.v1.ExecuteMission",
  "objective": {
    "type": "ARTIFACT",
    "artifact_id": "mission-7f3a"
  },
  "parameters": {
    "start_mode": "IMMEDIATE"
  }
}
```

This keeps OpenGrid centered on Entities, Tasks and Artifacts while allowing
vehicle-native mission formats such as MAVLink plans, MOOS behaviors or
vendor-specific AUV mission files.
