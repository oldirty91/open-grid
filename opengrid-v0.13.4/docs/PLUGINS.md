# Plugin Architecture

Plugins are OpenGrid's integration boundary. They are not another world-model concept.

A plugin may:

- Publish full entities
- Patch entity components
- Subscribe to changes
- Claim and execute tasks
- Publish task status
- Upload artifacts
- Publish its own health as an Entity

A plugin owns one or more external protocols and translates them into canonical OpenGrid concepts.

OpenGrid should never contain branches such as:

```python
if platform == "mavlink":
    ...
elif platform == "ros2":
    ...
```

Instead, protocol-specific behavior belongs in separate plugins.

## Planned plugin contract

- Manifest and version
- Stable plugin identity
- Authentication credentials
- Entity publication helper
- Task subscription and claim helper
- Artifact client
- Heartbeat and health
- Conformance tests
