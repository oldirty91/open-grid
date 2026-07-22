# ADS-B Plugin

OpenGrid supports local receiver and open-network inputs.

- `readsb_json`: polls `aircraft.json` from readsb/tar1090
- `sbs_tcp`: reads BaseStation/SBS messages, commonly port 30003
- `adsb_lol_rest`: polls the free/open adsb.lol compatible point API
- `opensky_rest`: polls OpenSky state vectors for a bounding box
- `websocket`: consumes provider or self-hosted JSON WebSockets

A broadly available official free/open ADS-B WebSocket was not identified, so the public open-network defaults use REST polling.
