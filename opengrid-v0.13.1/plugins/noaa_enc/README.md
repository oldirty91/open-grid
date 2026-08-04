# NOAA ENC plugin

Data-driven NOAA Electronic Navigational Chart adapter for OpenGrid.

The plugin discovers S-57 object-class layers from NOAA ENC Direct to GIS, queries
features for the current map bounds, caches returned GeoJSON features in its own
`plugin_noaa_enc` PostGIS schema, and registers map layers with OpenGrid. NOAA
ENC data never enters the core Entity or Track tables.

This source is for situational awareness and application development, not
certified navigation.
