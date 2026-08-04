# OpenGrid Map Engine

Offline MBTiles map library. Copy `.mbtiles` files into `./map-library` or upload them from the Artifacts page. The plugin scans the persistent volume, registers raster layers, and serves XYZ tiles locally. MBTiles TMS row numbering is converted automatically.

Raster MBTiles (`png`, `jpg`, `jpeg`, `webp`) are supported in v0.13. Vector PBF archives are detected but not registered until vector style support is added.
