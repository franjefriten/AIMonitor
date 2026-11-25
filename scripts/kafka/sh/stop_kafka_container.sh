#!/bin/bash
set -e

CONTAINER_NAME="kafka"

echo "Stopping Kafka container..."
docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
echo "Kafka container stopped."
