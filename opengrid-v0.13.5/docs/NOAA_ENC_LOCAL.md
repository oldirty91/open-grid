# Local NOAA ENC Adapter

The NOAA ENC adapter is local-first and works offline after import.

## Import

1. Open **Plugins** in its own tab.
2. Select **NOAA ENC**.
3. Under **Local ENC cells**, choose **Add ENC file**.
4. Upload an official S-57 base cell such as `US5RI1BE.000`.

The adapter stores the source file under `plugins/noaa_enc/data`, converts each S-57 feature class to GeoJSON with GDAL, and indexes the geometry in its plugin-owned PostGIS schema.

The same directory can also be populated manually while OpenGrid is stopped. On the next scan, `.000-.999` files are imported automatically.

## Updates

S-57 update files may be stored alongside the base cell. v0.13.3 accepts the files and imports each supplied file. Full sequential base/update application can be expanded in a later release.

## Storage boundary

ENC features are published as core `GEOENTITY` records in `entities_current`. The plugin-owned schema remains an import/index cache, while the core Entity record is the canonical operator-visible representation.
