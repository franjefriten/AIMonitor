#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_PATH="${SCRIPT_DIR}/../otel-collector.yaml"
IMAGE_NAME="otel/opentelemetry-collector-contrib:latest"
CONTAINER_NAME="${OTEL_COLLECTOR_CONTAINER_NAME:-otel-collector}"
BEARER_TOKEN="${OTEL_COLLECTOR_BEARER_TOKEN:-integration-test-token}"

if [ ! -f "$CONFIG_PATH" ]; then
  echo "OpenTelemetry Collector config file not found: $CONFIG_PATH" >&2
  exit 1
fi

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  echo "Pulling OpenTelemetry Collector image..."
  docker pull "$IMAGE_NAME"
fi

echo "Starting OpenTelemetry Collector container..."
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d \
  --name "$CONTAINER_NAME" \
  -p 4318:4318 \
  -p 13133:13133 \
  -e "OTEL_COLLECTOR_BEARER_TOKEN=${BEARER_TOKEN}" \
  -v "${CONFIG_PATH}:/etc/otelcol-contrib/config.yaml:ro" \
  "$IMAGE_NAME" \
  --config=/etc/otelcol-contrib/config.yaml

echo "OpenTelemetry Collector running with OTLP/HTTP at http://localhost:4318"
