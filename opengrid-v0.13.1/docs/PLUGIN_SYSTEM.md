# Plugin System

Plugins are administrative integrations, not Entities.

A plugin may register itself, report heartbeats and metrics, expose configuration metadata, publish Entities, consume Tasks, and create Artifacts. Plugin status is visible only on the Plugins page and plugin API.

## Reference AIS plugin

The first reference plugin runs as an independent Docker container and supports replay from decoded JSONL records, AIS NMEA over UDP, AIS NMEA over TCP, Track Entity publication, plugin heartbeat and metrics, and logical enable/disable.
