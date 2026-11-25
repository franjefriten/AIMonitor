#!/bin/bash
set -eu

CONTAINER_NAME="${1:-kafka}"

echo "Stopping Kafka container '${CONTAINER_NAME}'..."
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

echo "Removing Kafka-related Docker volumes..."
for volume in $(docker volume ls -q --filter name=kafka 2>/dev/null || true); do
  if [ -n "$volume" ]; then
    echo "  -> removing volume $volume"
    docker volume rm -f "$volume" >/dev/null 2>&1 || true
  fi
done

docker volume prune -f >/dev/null 2>&1 || true

echo "Kafka container and related volumes have been cleaned."
