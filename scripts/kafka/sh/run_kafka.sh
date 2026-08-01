#!/bin/bash
set -e

PORT="9092"
HOST="0.0.0.0"
IMAGE_NAME="apache/kafka:latest"
CONTAINER_NAME="kafka"

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  echo "Pulling Kafka image..."
  docker pull "$IMAGE_NAME"
fi

echo "Starting Kafka container..."
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d \
    --name "$CONTAINER_NAME" \
    -p "${PORT}:${PORT}" \
    -e KAFKA_NODE_ID=1 \
    -e KAFKA_PROCESS_ROLES=broker,controller \
    -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:${PORT},CONTROLLER://0.0.0.0:9093 \
    -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://127.0.0.1:${PORT} \
    -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@127.0.0.1:9093 \
    -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
    -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
    -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
    -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
    "$IMAGE_NAME"
echo "Ready! Kafka running in http://${HOST}:${PORT}"