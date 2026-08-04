# Persistent tracks

The map now hydrates up to 24 hours of persisted location samples for every entity when the application loads, then merges live WebSocket samples into the same track cache. Selecting an entity draws the complete hydrated track rather than only positions observed after the last page refresh.
