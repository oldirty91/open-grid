# Geo-Entities

OpenGrid Geo-Entities use one of four operator geometry definitions:

- `Point`
- `LineString`
- `Polygon`
- `Ellipse`

Purpose and other operational meaning are optional attributes rather than
separate core geometry types.

## Vertical model

OpenGrid uses meters relative to mean sea level for all canonical vertical
position data:

- `location.elevation_m`
- `volume.minimum_elevation_m`
- `volume.maximum_elevation_m`

Altitude and depth may be published separately as derived or sensor-reported
measurements, but they do not replace canonical elevation.

Ellipses retain an editable definition while also publishing a polygon
approximation for rendering and spatial queries.
