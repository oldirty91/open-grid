# Entity Model

OpenGrid preserves three operator-facing Entity categories, following the world-model principles used throughout the project.

## Asset

An Asset is something OpenGrid can control, task, or otherwise operate. Examples include UAVs, USVs, AUVs, rovers, and taskable fixed sensors.

Use `ontology.template = ASSET`. Legacy `SENSOR` records remain displayed with Assets when they advertise operational capabilities.

## Track

A Track is an observation or contact produced by a sensor or external data source. AIS vessels, ADS-B aircraft, radar contacts, and fused contacts are Tracks. A Track is not directly controlled.

Use `ontology.template = TRACK`.

## Geo-Entity

A Geo-Entity is geographic operational information represented as a point, line, polygon, multipolygon, or ellipse. Ellipses are stored as polygon approximations in GeoJSON. It may be user-authored, imported, or supplied by a plugin.

Core persistent Geo-Entities use `ontology.template = GEOENTITY` and a geometry component such as:

```json
{
  "ontology": {"template": "GEOENTITY"},
  "geometry": {
    "geojson": {
      "type": "Polygon",
      "coordinates": [[[-71.4,41.4],[-71.3,41.4],[-71.3,41.5],[-71.4,41.4]]]
    }
  }
}
```

High-volume plugin GIS features, such as an ENC cell, remain in plugin-owned storage but are presented in the Geo-Entities drawer. This preserves the same operator concept without loading static reference data into the dynamic Entity/Track database.
