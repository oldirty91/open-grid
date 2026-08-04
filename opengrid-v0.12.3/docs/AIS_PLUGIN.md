# AIS Plugin

The AIS plugin supports four input modes.

## UDP

The plugin listens for `!AIVDM` or `!AIVDO` NMEA sentences on a configured local
address and port.

## TCP

The plugin connects to a configured TCP server and reads newline-delimited AIS
NMEA sentences.

## WebSocket

### AISStream.io

The plugin connects to `wss://stream.aisstream.io/v0/stream` by default and
sends the configured API key, bounding boxes, MMSI filters and message-type
filters immediately after connection.

The API key remains in the backend/plugin configuration path and is never used
by browser-side WebSocket code.

### Generic

A generic JSON WebSocket may provide:

- AISStream-style messages,
- decoded AIS dictionaries,
- provider-specific JSON compatible with the AIS normalization fields.

## Runtime reconfiguration

The plugin periodically reads its OpenGrid registry configuration. When the
configuration changes, it closes the current input source and reconnects.
