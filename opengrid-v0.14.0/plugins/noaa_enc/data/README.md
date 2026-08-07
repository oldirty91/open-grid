# Local ENC data

Place official NOAA S-57 cells (`.000` base files and optional numbered updates) in this directory. The NOAA ENC adapter scans the directory, converts supported feature classes with GDAL, and stores them in its plugin-owned PostGIS schema for offline use.

Files can also be added and removed from **Plugins → NOAA ENC → Local ENC cells**.
