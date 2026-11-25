#!/bin/bash
set -e

CONTAINER_NAME="${PROMETHEUS_CONTAINER_NAME:-prometheus}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed" >&2
  exit 127
fi

docker restart "$CONTAINER_NAME"

echo "Prometheus restarted successfully."
