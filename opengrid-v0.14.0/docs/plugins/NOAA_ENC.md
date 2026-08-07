# NOAA ENC plugin

`plugins/noaa_enc` is OpenGrid's first data-driven GIS plugin. It connects to
NOAA ENC Direct to GIS, discovers matching S-57 object-class layers, and
registers them with the OpenGrid map layer manager.

## Storage

The plugin owns the PostGIS schema `plugin_noaa_enc`:

* `layers` records discovered source layers.
* `features` caches bounded GeoJSON queries as PostGIS geometry.
* `ingest_jobs` records synchronization work.

If NOAA is unavailable, the plugin serves cached features for a requested map
extent when possible.

## Map behavior

The map requests only enabled layers and only for the visible map bounds.
Initial preferred classes include depth areas, depth contours, soundings,
aids to navigation, wrecks, obstructions, land areas, and coastlines. Layer
availability ultimately depends on the configured NOAA MapServer.

The source is for situational awareness and software development, not certified
navigation.
