# Map Engine and offline MBTiles

OpenGrid v0.13 introduces a local Map Engine plugin. Raster MBTiles archives can be imported from the Artifacts page or copied into `map-library/`. The library is mounted persistently, scanned automatically, and served as local XYZ tiles. This avoids repeated network downloads and supports disconnected operation.

## Supported in v0.13

- Raster MBTiles: PNG, JPEG, and WebP
- Persistent local archive
- TMS-to-XYZ row conversion
- Browser and HTTP tile caching
- Per-map visibility from the Artifacts page

Vector PBF MBTiles are detected but intentionally not registered until vector style metadata is supported.
