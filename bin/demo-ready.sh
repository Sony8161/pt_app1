#!/usr/bin/env bash
# Script: Get the LocalStack demo ready to present
# Purpose: Empty the demo database, load the sample company through the real API (two managers, six employees,
#          four projects dated relative to today), and give every account a short, memorable username and password,
#          so nothing has to be copied from a one-time dialog. Also adds one "new hire" whose first sign-in forces
#          a password change. Run it right before you present, and again after every practice run.
# Usage: ./bin/demo-ready.sh        (needs ./bin/demo-postgres.sh and ./bin/start-dev.sh to be running)

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" > /dev/null 2>&1 || exit 1; pwd -P)"
API="${API:-http://localhost:3001/api/pm-api}"

# bcrypt hashes of the demo passwords below (these are public, local-only demo passwords)
HASH_DEMO='$2b$12$RkJqVC2.CPiS5LG7NP3o6OICtJw4sP5LGDjSWnct7Z6CkIeT1CeYO'      # Demo1234!
HASH_WELCOME='$2b$12$gV5tKex5G214NyI5bAg0Me654zEyz1QWomfXmpXzXV1RBRens4Pvu'   # Welcome123!

psql_() { docker exec -i pm-demo-postgres psql -U postgres -q -v ON_ERROR_STOP=1 "$@"; }
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }

echo "1/4 Clearing the demo database..."
"$SCRIPT_DIR/demo-reset.sh" > /dev/null

echo "2/4 Loading the sample company through the API..."
# The reset leaves the first admin needing a password change; the API refuses other calls until then, so lift it for seeding.
psql_ -c "UPDATE users SET must_change_password = false WHERE username = 'admin1'"
TOKEN=$(curl -s -m 60 -X POST "$API/auth/login" -H 'Content-Type: application/json' \
    -d '{"username":"admin1","password":"ChangeMe123!"}' | json "d['access_token']")
AUTH=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
curl -s -m 120 -X POST "$API/admin/seed-demo" "${AUTH[@]}" | json "d['message']"

MARIA_ID=$(psql_ -tA -c "SELECT id FROM users WHERE email LIKE 'maria.lopez@%'")
curl -s -m 60 -X POST "$API/users" "${AUTH[@]}" -d "{\"name\":\"Nina Park\",\"email\":\"nina.park@demo.acme.example\",\"job_title\":\"Junior Designer\",\"role\":\"employee\",\"manager_id\":\"$MARIA_ID\",\"salary\":38}" > /dev/null

echo "3/4 Setting readable usernames and passwords..."
psql_ <<SQL
UPDATE users u SET username = v.username
FROM (VALUES
  ('maria.lopez@%', 'maria1'), ('james.carter@%', 'james1'), ('alex.kim@%', 'alex01'), ('priya.shah@%', 'priya1'),
  ('tom.becker@%', 'tom001'), ('lena.fischer@%', 'lena01'), ('omar.haddad@%', 'omar01'), ('sofia.rossi@%', 'sofia1'),
  ('nina.park@%', 'nina01')
) AS v(pattern, username) WHERE u.email LIKE v.pattern;
UPDATE users SET password_hash = '$HASH_DEMO', must_change_password = false WHERE username <> 'nina01';
UPDATE users SET password_hash = '$HASH_WELCOME', must_change_password = true WHERE username = 'nina01';
SQL

echo "4/4 Checking sign-in..."
for who in "admin1 Demo1234!" "maria1 Demo1234!" "alex01 Demo1234!" "nina01 Welcome123!"; do
    set -- $who
    curl -s -m 60 -X POST "$API/auth/login" -H 'Content-Type: application/json' -d "{\"username\":\"$1\",\"password\":\"$2\"}" \
        | grep -q access_token || { echo "ERROR: $1 cannot sign in"; exit 1; }
done

cat <<'TXT'

Ready. Open http://localhost:3000

  Username   Password      Who                      Use it to show
  ---------  ------------  -----------------------  --------------------------------------------
  admin1     Demo1234!     System Admin (admin)     dashboard, create/archive/restore, people
  maria1     Demo1234!     Maria Lopez (manager)    Website Redesign: tick, complete, assign
  james1     Demo1234!     James Carter (manager)   the overdue and at-risk projects
  alex01     Demo1234!     Alex Kim (employee)      "My work": no money, only my milestone
  nina01     Welcome123!   Nina Park (new hire)     first sign-in forces a new password (once)
  priya1 sofia1 tom001 lena01 omar01: more employees, all Demo1234!

Run this script again to put everything back (it also undoes Nina's password change).
TXT
