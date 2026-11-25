#!/bin/bash
set -e

CONTAINER_NAME="${OTEL_COLLECTOR_CONTAINER_NAME:-otel-collector}"
IMAGE_NAME="otel/opentelemetry-collector-contrib:latest"

echo "Stopping OpenTelemetry Collector container..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Removing OpenTelemetry Collector image..."
docker rmi -f "$IMAGE_NAME" 2>/dev/null || true

echo "OpenTelemetry Collector cleanup complete."
