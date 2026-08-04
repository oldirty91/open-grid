#!/bin/sh
set -eu
echo "=== containers ==="
docker compose ps
echo
echo "=== API health ==="
curl -fsS http://localhost:8000/health || true
echo
echo "=== recent API logs ==="
docker compose logs --tail=120 api
echo
echo "=== recent dependency logs ==="
docker compose logs --tail=60 postgres nats minio
