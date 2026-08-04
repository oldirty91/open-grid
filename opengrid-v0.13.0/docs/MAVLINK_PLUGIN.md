# MAVLink Plugin

The v0.7 plugin is the first bidirectional OpenGrid integration. It translates
MAVLink telemetry into an Asset Entity and translates OpenGrid Tasks into
MAVLink navigation behavior.

## Supported telemetry

- HEARTBEAT
- GLOBAL_POSITION_INT
- ATTITUDE
- SYS_STATUS
- BATTERY_STATUS
- GPS_RAW_INT

## Supported Tasks

- Navigate
- Loiter
- ReturnToLaunch

## Connections

- `udp_listen`
- `udp_remote`
- `tcp`
- `serial`

Use SITL first. A MAVLink router is recommended when OpenGrid and a traditional
ground-control station need simultaneous access to one vehicle.
