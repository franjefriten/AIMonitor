#!/bin/bash
set -e

CONTAINER_NAME="prometheus"
IMAGE_NAME="prom/prometheus"

echo "Stopping Prometheus container..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Removing Prometheus image..."
docker rmi -f "$IMAGE_NAME" 2>/dev/null || true

echo "Prometheus cleanup complete."
