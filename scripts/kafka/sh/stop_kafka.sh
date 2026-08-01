#!/bin/bash
set -e

CONTAINER_NAME="kafka"
IMAGE_NAME="apache/kafka:latest"

echo "Stopping Kafka container..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Removing Kafka image..."
docker rmi -f "$IMAGE_NAME" 2>/dev/null || true

echo "Kafka cleanup complete."
