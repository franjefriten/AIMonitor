#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${SCRIPT_DIR}/../prometheus.yaml"
IMAGE_NAME="prom/prometheus"
CONTAINER_NAME="${PROMETHEUS_CONTAINER_NAME:-prometheus}"
HOST_PORT="${PROMETHEUS_HOST_PORT:-9090}"

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  echo "Pulling Prometheus image..."
  docker pull "$IMAGE_NAME"
fi

echo "Starting Prometheus container..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --add-host "host.docker.internal:host-gateway" \
  -p "${HOST_PORT}:9090" \
  -v "${CONFIG_PATH}:/etc/prometheus/prometheus.yml" \
  "$IMAGE_NAME"

echo "Ready! Prometheus running at http://localhost:${HOST_PORT}"