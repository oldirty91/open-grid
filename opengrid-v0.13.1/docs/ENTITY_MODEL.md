# Entity Model

An Entity is a stable identifier plus a flexible set of components.

```json
{
  "entity_id": "asset-alpha",
  "components": {
    "ontology": {
      "template": "ASSET",
      "domain": "MARITIME",
      "platform_type": "USV"
    },
    "location": {},
    "limits": {},
    "equipment": {},
    "resources": {},
    "capabilities": {},
    "task_catalog": {}
  }
}
```

No universal component set is required.

## Guidance

- Validate known components when definitions exist.
- Preserve unknown components.
- Do not require unrelated components.
- Record provenance with every accepted update.
- Prefer component PATCH for independent publishers.
- Treat platform type as descriptive, not as the primary behavior switch.

## Capability semantics

An available capability means the responsible plugin believes it is usable now.

Example:

```json
{
  "capabilities": {
    "available": [
      {"name": "navigate"},
      {
        "name": "side_scan_sonar",
        "constraints": {
          "recommended_speed_mps": {"minimum": 1.0, "maximum": 3.0}
        }
      },
      {
        "name": "launch_flare",
        "constraints": {"remaining_uses": 3}
      }
    ]
  }
}
```

Installed equipment and resources remain separate so operators can distinguish installed-but-failed equipment from currently usable capability.
