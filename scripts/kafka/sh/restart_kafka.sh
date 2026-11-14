#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed" >&2
  exit 127
fi

"${SCRIPT_DIR}/stop_kafka_container.sh"
"${SCRIPT_DIR}/run_kafka.sh"

echo "Kafka restarted successfully."
