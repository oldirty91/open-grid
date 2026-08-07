# ENC map presentation

ENC objects are ordinary `GEOENTITY` records. Presentation rules do not alter that data model.

## Rendering order

ENC polygons, lines, points, and soundings render above the basemap. Tracks, Assets, task routes, task waypoints, and selections are always promoted above ENC content.

## Soundings

`SOUNDG` entities retain full geometry and attributes but render as small depth labels using `VALSOU` where available.

## Visibility

The Entity inspector can hide an individual Geo-Entity or its complete class. Preferences are browser-local and affect map rendering only. Hidden objects remain in the drawer and can be restored.

## Colors

Buoys, beacons, and lights use imported S-57 `COLOUR` values, including red (`3`) and green (`4`).
