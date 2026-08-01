#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${SCRIPT_DIR}/../prometheus.yaml"
IMAGE_NAME="prom/prometheus"
CONTAINER_NAME="prometheus"

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  echo "Pulling Prometheus image..."
  docker pull "$IMAGE_NAME"
fi

echo "Starting Prometheus container..."
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

docker run -d \
  --name "$CONTAINER_NAME" \
  -p "9090:9090" \
  -v "${CONFIG_PATH}:/etc/prometheus/prometheus.yaml" \
  "$IMAGE_NAME"

echo "Ready! Prometheus running at http://localhost:9090"