#!/usr/bin/env bash
# Script: Reset the LocalStack demo to a clean state
# Purpose: Erase all demo data so the next run starts from the first login (admin1 / ChangeMe123!). Takes a few
#          seconds; if the tables are missing it falls back to a full reset that restarts the Lambda (about 3 minutes).
#          Run it between practice runs. Needs ./bin/start-dev.sh to have been run once (it deploys the API).
# Usage: ./bin/demo-reset.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" > /dev/null 2>&1 || exit 1; pwd -P)"
API="${API:-http://localhost:3001/api/pm-api}"

PSQL=(docker exec -i pm-demo-postgres psql -U postgres -q -v ON_ERROR_STOP=1)
# bcrypt hash of the documented first-login password ChangeMe123! (the public local default, see the README)
ADMIN_HASH='$2b$12$AixHgIZtZdV6poBIfnBap.aQX/e2SfQfZLY6ThWBt/Dvq5Oenusya'

# Fast path (a few seconds): the tables exist, so just empty them and put the first admin back. The Lambda stays warm.
if docker exec pm-demo-postgres psql -U postgres -tAc "select to_regclass('public.users') is not null" 2> /dev/null | grep -q t; then
    "${PSQL[@]}" <<SQL
SET client_min_messages = warning;
TRUNCATE users CASCADE;
INSERT INTO users (username, password_hash, name, email, job_title, role, salary, must_change_password)
VALUES ('admin1', '$ADMIN_HASH', 'System Admin', 'admin@acme.example', 'Administrator', 'admin', 0, true);
SQL
    if curl -s -m 60 -X POST "$API/auth/login" -H 'Content-Type: application/json' \
        -d '{"username":"admin1","password":"ChangeMe123!"}' | grep -q access_token; then
        echo "Ready. Sign in as admin1 / ChangeMe123! at http://localhost:3000"; exit 0
    fi
    echo "Fast reset did not work; doing a full reset..."
fi

"$SCRIPT_DIR/demo-postgres.sh" --reset

# The Lambda process remembers that it already created the tables, so it must be restarted too.
docker ps -q --filter 'name=lambda-coding-workshop-pm-api' | xargs -r docker rm -f > /dev/null || true

echo "Waiting for the API to start again (the first call after a restart can take up to a minute)..."
for i in $(seq 1 6); do
    if curl -s -m 100 "$API/health" | grep -q '"database":"ok"'; then
        curl -s -m 60 -X POST "$API/auth/login" -H 'Content-Type: application/json' \
            -d '{"username":"admin1","password":"ChangeMe123!"}' | grep -q access_token \
            && { echo "Ready. Sign in as admin1 / ChangeMe123! at http://localhost:3000"; exit 0; }
    fi
    sleep 3
done
echo "ERROR: the API did not come back. Run ./bin/start-dev.sh to redeploy it."; exit 1
