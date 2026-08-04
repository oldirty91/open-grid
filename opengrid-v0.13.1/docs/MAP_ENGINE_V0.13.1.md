# OpenGrid Map Engine v0.13.1

This release begins the cohesive Map Engine refactor.

## Persistent tracks

The API now exposes `GET /api/v1/tracks/history` for bulk persisted history. The map hydrates 24 hours of database-backed history at startup and then appends WebSocket updates.

## Offline Map Library

Copy `.mbtiles` files into `./map-library`. The dedicated Map Engine container scans the directory recursively every five seconds, validates SQLite metadata, registers raster layers, and serves tiles through the core API proxy. Browser upload is no longer required.

## NOAA ENC compatibility

NOAA ENC remains a GIS provider during the migration. Its layers and MBTiles layers both register through the existing unified GIS layer registry, allowing the frontend to consume both without direct access to plugin-internal hostnames.

## Next refactor stages

- Durable map-layer registry owned by the Map Engine
- NOAA cell download/import workflow
- Offline ENC vector-tile generation
- GeoTIFF/COG importer
- Map package export/import
