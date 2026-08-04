# OpenGrid Python SDK v0.1

The SDK isolates adapters from routine API plumbing. Its public API is versioned independently from the server.

## Compatibility
- OpenGrid server: 0.10.x
- SDK package: 0.1.x
- Adapter API: v1

Adapters should depend on the narrow `OpenGridAdapter` and `OpenGridClient` interfaces instead of embedding endpoint calls. Backward-compatible additions remain in the same minor SDK line; breaking changes require a new adapter API version.

## Local use
```bash
pip install ./sdk/python
```

See `sdk/python/examples/basic_adapter.py`.
