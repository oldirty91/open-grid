# GIS layer architecture

OpenGrid separates operational objects from reference geospatial data.

* **Entities** remain dynamic operational things.
* **Tasks** express operational intent.
* **Artifacts** are persistent data, whether they are inputs or outputs.
* **Plugin GIS layers** are high-volume reference data owned by the plugin that
  supplies them.

GIS plugins register layer descriptors through `PUT /api/v1/plugins/{id}/gis-layers`.
The map discovers them through `GET /api/v1/gis/layers` and requests bounded
GeoJSON through the core proxy. The core does not store ENC features in Entity,
Track, or Artifact tables.

Plugin data lifecycle is independent of plugin runtime lifecycle. Disabling a
plugin leaves its schema intact. Removing the plugin service makes its layers
unavailable. Purging plugin storage should be an explicit administrative action.
