# Fixed Camera Adapter

Configure one or more cameras with `CAMERAS_JSON`. Each camera supports `id`, `name`, `latitude`, `longitude`, `altitude_m`, `direction_deg`, `horizontal_fov_deg`, `range_m`, `snapshot_url`, `stream_url`, and `stream_type`.

The adapter never generates synthetic imagery. `CaptureSnapshot` requires a real `snapshot_url`. Live viewing uses the configured snapshot or stream URL. `RecordForDuration` currently publishes an honest recording-reference Artifact unless a recorder backend is added.
