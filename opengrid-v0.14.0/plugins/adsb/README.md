# ADS-B Plugin

Supported sources:

- replay JSONL
- local readsb/tar1090 `aircraft.json`
- SBS/BaseStation TCP (commonly port 30003)
- adsb.lol compatible REST point queries
- OpenSky state-vector REST queries
- generic JSON WebSocket

No broadly available, official free/open ADS-B WebSocket was identified for this
release. The open-network options are therefore REST polling, while WebSocket
support remains available for provider or self-hosted feeds.
