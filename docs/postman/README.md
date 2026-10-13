# Postman collection: ACME Project Tracker API

A complete, self-checking test flow for the API: **126 requests, 502 assertions**, with the expected JSON
response saved as an example on every request.

| File | What it is |
|---|---|
| `acme-pm-api.postman_collection.json` | The collection (import this) |
| `local.postman_environment.json` | `http://localhost:8000`, the API run directly with uvicorn |
| `localstack.postman_environment.json` | `http://localhost:3001/api/pm-api`, via `./bin/start-dev.sh` |
| `aws.postman_environment.json` | Your CloudFront URL (edit `baseUrl`; the admin password is `terraform output -raw bootstrap_admin_password`) |
| `build_collection.py` | Generator: one spec produces the tests **and** runs the flow to capture the examples |

## Run it

1. Start the API against an **empty database**. The first admin (`admin1`) is created on the first request, and the
   flow creates its own managers, employees and projects.
   ```sh
   cd backend/pm-api && source .venv/bin/activate
   POSTGRES_NAME=pm_postman uvicorn app.main:app --port 8000   # create the pm_postman database first
   ```
2. In Postman: **Import** the collection and an environment, pick the environment, then **Run collection** (in order).
   Or from the terminal:
   ```sh
   npx newman run docs/postman/acme-pm-api.postman_collection.json \
       -e docs/postman/local.postman_environment.json
   ```
3. Re-running needs a fresh database, because the first request signs in with the one-time admin password.
   To keep a database, set `initial_admin_password` to the admin's current password and skip folder `01 Auth`.

## What it walks through

| Folder | Shows |
|---|---|
| 00 Health | liveness and database check |
| 01 Auth | first login, forced password change, weak passwords, token revocation, 401/403 |
| 02 Users | create people (generated username and one-time password), role rules, salary visibility, archive/restore |
| 03 Projects | admin creates for one manager, visibility (404, not 403), budget edits, search and paging |
| 04 Milestones | dates and hours must fit the project; marking a milestone done |
| 05 Team | an employee gives one project their full 8-hour day, overlapping assignments are refused |
| 06 Time | 8 hours a day cap, only inside assignment dates, never the future |
| 07 Costs | non-labor costs and the budget math |
| 08 Reports | overview, allocation and personal dashboard |
| 09 Project lifecycle | complete (releases the team), archive, restore |
| 10 Admin | demo data |

Every error follows one shape: `{"error": {"code", "message", "details": []}}`. Every request in the collection
asserts its status code and the important fields, and stores the ids and tokens the next request needs
(`admin_token`, `manager_token`, `employee_token`, `project_id`, ...). Dates are relative to today, so it works any day.

## Regenerate

```sh
# with the API running on port 8001 against an empty database
cd backend/pm-api && source .venv/bin/activate
python ../../docs/postman/build_collection.py --base-url http://127.0.0.1:8001
```
It runs the whole flow first and refuses to write the files if any check fails, so the saved examples are always
real output. Access tokens in examples are masked. The one-time passwords shown in examples belong to throw-away
accounts in a throw-away database.
