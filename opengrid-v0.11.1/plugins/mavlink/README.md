# MAVLink Plugin

The MAVLink plugin publishes discovered vehicles as OpenGrid Asset Entities and
executes a small initial task set:

- Navigate
- Loiter
- Return to Launch

Supported connections:

- UDP listener
- UDP remote endpoint
- TCP client
- Serial device

The recommended first test is ArduPilot SITL or PX4 SITL. Keep QGroundControl
connected through mavlink-router or another MAVLink routing layer so OpenGrid is
not the only observer.
