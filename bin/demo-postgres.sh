#!/usr/bin/env bash
# Script: Docker PostgreSQL for the LocalStack demo
# Purpose: LocalStack Lambda containers reach the host at 172.17.0.1 (the Docker bridge), but the system
#          PostgreSQL usually listens on 127.0.0.1 only, and changing that needs sudo. This starts a separate
#          PostgreSQL 17 container published on the bridge address instead: no sudo, no change to the system
#          database, and a clean database for each demo (use --reset).
# Usage: ./bin/demo-postgres.sh [--reset | --stop]

set -e

NAME="pm-demo-postgres"
VOLUME="pm-demo-pgdata"
HOST_IP="172.17.0.1"
IMAGE="postgres:17-alpine"

case "${1:-}" in
    -h|--help)
        sed -n 2,9p "$0" | sed 's/^# \{0,1\}//'
        exit 0 ;;
    --stop)
        docker rm -f "$NAME" > /dev/null 2>&1 || true
        echo "Stopped $NAME (data kept in volume $VOLUME; use --reset to erase it)"
        exit 0 ;;
    --reset)
        docker rm -f "$NAME" > /dev/null 2>&1 || true
        docker volume rm "$VOLUME" > /dev/null 2>&1 || true
        echo "Erased the demo database" ;;
esac

docker info > /dev/null 2>&1 || { echo "ERROR: Docker is not running"; exit 1; }
ip -4 addr show docker0 2> /dev/null | grep -q "$HOST_IP" || { echo "ERROR: $HOST_IP (docker0) not found; this script is for Linux"; exit 1; }

if [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2> /dev/null)" = "true" ]; then
    echo "$NAME is already running on $HOST_IP:5432"
else
    docker rm -f "$NAME" > /dev/null 2>&1 || true
    docker run -d --name "$NAME" --restart unless-stopped \
        -p "$HOST_IP:5432:5432" \
        -e POSTGRES_PASSWORD=postgres123 \
        -v "$VOLUME:/var/lib/postgresql/data" \
        "$IMAGE" > /dev/null
fi

for i in $(seq 1 30); do
    if docker exec "$NAME" pg_isready -U postgres -q 2> /dev/null; then
        echo "PostgreSQL is ready on $HOST_IP:5432 (user postgres, database postgres)"
        exit 0
    fi
    sleep 1
done
echo "ERROR: PostgreSQL did not become ready"; docker logs --tail 20 "$NAME"; exit 1
