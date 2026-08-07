# Sensor collections

Sensors are flexible Entity components:

```json
{
  "sensors": {
    "items": [
      {
        "sensor_id": "main-camera",
        "type": "VIDEO_CAMERA",
        "name": "Main Camera",
        "status": {"state": "ONLINE"},
        "mount": {"azimuth_deg": 135, "elevation_deg": -5},
        "field_of_view": {
          "horizontal_deg": 65,
          "vertical_deg": 35,
          "range_m": 500
        },
        "media": {
          "stream_url": "...",
          "stream_type": "MP4",
          "live_available": true
        },
        "properties": {}
      }
    ]
  }
}
```

Unknown sensor types and properties remain valid. The map applies passive
coverage rules only to types it recognizes.
