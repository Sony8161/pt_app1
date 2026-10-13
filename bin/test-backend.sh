#!/usr/bin/env bash
# Script: Backend Tests
# Purpose: Lint and test the pm-api backend against a local PostgreSQL
# Usage: ./test-backend.sh [pytest args...]

set -e

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    echo "Usage: $0 [pytest args...]"
    echo "Lint (ruff), scan (bandit) and test (pytest + coverage) the pm-api backend"
    echo ""
    echo "Requirements:"
    echo "  - python3.13 and a local PostgreSQL (postgres / postgres123 on localhost:5432)"
    echo "  - Tests use a separate database named pm_test; it is created if missing"
    echo ""
    echo "Examples:"
    echo "  $0                      # everything"
    echo "  $0 -k overlap           # only tests matching 'overlap'"
    exit 0
fi

echo "==============================="
echo "Coding Workshop - Backend Tests"
echo "==============================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" > /dev/null 2>&1 || exit 1; pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." > /dev/null 2>&1 || exit 1; pwd -P)"
SERVICE_DIR="$PROJECT_ROOT/backend/pm-api"

command -v python3.13 > /dev/null 2>&1 || { echo "ERROR: 'python3.13' is missing. Aborting..."; exit 1; }
pg_isready -q || { echo "ERROR: PostgreSQL is not running on localhost:5432. Start it (see ./bin/start-dev.sh)."; exit 1; }

cd "$SERVICE_DIR"

# Isolated virtualenv; the service folder itself is kept clean for Lambda packaging (see .gitignore)
if [ ! -d .venv ]; then
    echo "INFO: Creating virtual environment..."
    python3.13 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

REQS_HASH=$(cat requirements.txt requirements-dev.txt | md5sum | cut -d' ' -f1)
if [ "$(cat .venv/.reqs_hash 2>/dev/null)" != "$REQS_HASH" ]; then
    echo "INFO: Installing dependencies..."
    pip install --quiet -r requirements-dev.txt bandit
    echo "$REQS_HASH" > .venv/.reqs_hash
fi

echo "INFO: ruff (lint)"
ruff check app tests

echo "INFO: bandit (security scan, same as CI)"
(cd "$PROJECT_ROOT" && bandit -q -r ./backend)

echo "INFO: pytest"
python -m pytest tests -p no:warnings --cov --cov-report=term-missing:skip-covered --cov-fail-under=80 "$@"
