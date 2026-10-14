# pm-api: ACME Project Tracker API

FastAPI on AWS Lambda (Mangum) with PostgreSQL. Projects are built from milestones; people are assigned to milestones;
hours, cost and risk are calculated from dates. Nothing is ever deleted: removing means archiving, and only admins see the archive.

Interactive API docs: `/docs` (Swagger) and `/openapi.json` when the API runs directly with `uvicorn`.
A 138-request Postman collection with saved example responses is in [`docs/postman`](../../docs/postman/README.md).

## Run it

```sh
cd backend/pm-api
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
POSTGRES_NAME=pm_dev uvicorn app.main:app --port 8000      # create the empty database pm_dev first
```

Sign in as `admin1` / `ChangeMe123!` (you must change the password), then `POST /admin/seed-demo` loads a sample company.
On LocalStack use `./bin/demo-postgres.sh` and `./bin/start-dev.sh` from the repository root (see `docs/DEMO.md`).

| Setting | Meaning | Default |
|---|---|---|
| `IS_LOCAL` | Local (no SSL, documented dev defaults) or cloud (`sslmode=require`, secrets required) | `true` |
| `POSTGRES_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASS` | Database connection | `localhost`, `5432`, `postgres`, `postgres`, `postgres123` |
| `JWT_SECRET` | Signing key for login tokens. Required in the cloud; Terraform generates it | local constant |
| `BOOTSTRAP_ADMIN_PASSWORD` | First admin's one-time password. Required in the cloud; Terraform generates it | `ChangeMe123!` locally |
| `ACCESS_TOKEN_TTL_MINUTES` | Login token lifetime | `480` |
| `APP_ENV`, `AUTO_MIGRATE` | Environment label; run migrations on first request | `local`, `true` |

## How it is organised

```
app/
  main.py          builds the app: routers, error handlers, middleware, /health
  config.py        settings from the environment
  db.py            one shared connection per Lambda container, SQL migrations, TransactionMiddleware
  core/            errors (one error shape), security (bcrypt, JWT), deps (current user, roles),
                   dates (UTC "today", freezable in tests), money (compare to the cent), observability (access log)
  domains/<name>/  router.py (URLs), schemas.py (validation), service.py (the rules), repository.py (SQL)
                   auth, users, projects, milestones, deliverables, assignments, costs, reports, admin
  migrations/      001_initial.sql, 002_milestone_work.sql (plain SQL, applied once, in order, under a lock)
  seed.py          first admin and the sample company
```

One request is one database transaction: the response is held until the commit succeeds, so a client never sees success for
work that failed to save. Business rules live only in `service.py`; SQL lives only in `repository.py`.

## The rules that matter

- **Roles.** Admin runs the system (creates projects for a manager, people, archives). A manager runs their own projects
  (milestones, deliverables, team, costs). An employee sees only the work they are assigned to and never any money.
  Permissions are enforced here, never only in the UI. What a person may not see returns 404, not 403.
- **Milestones are the unit of work.** An employee works one milestone per day; the API refuses overlapping assignments
  (across projects too) and names the clash. Every Monday to Friday of an assignment is an 8-hour shift:
  hours = working days x 8, labor cost = hours x the person's hourly `salary`. Nothing is typed in.
- **Risk is calculated** from dates, hours and money (see `domains/projects/metrics.py`) and always comes with its reasons.
- **No DELETE.** Every removal is `POST .../archive`; a test checks the API has no DELETE operation.
  Completing a milestone requires every deliverable ticked, a review note is kept, and it moves to the archive.
- **Sessions.** bcrypt passwords, HS256 tokens (8 hours), `token_version` revokes every older token on a password change or reset,
  `POST /auth/refresh` issues a fresh token, a generated first password must be changed at first sign-in.
- **Errors.** Always `{"error": {"code", "message", "details": [{"field", "message"}]}}` with 400 (validation), 401, 403, 404, 409 (conflict), 503.
- **Logs.** One JSON line per request (`method`, `path`, `status`, `ms`, `request_id`; never the query, headers or body) and an
  `X-Request-Id` response header. `aws logs tail /aws/lambda/<function> --follow` shows them.

## Endpoints

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login`, `GET /auth/me`, `POST /auth/refresh`, `POST /auth/change-password` |
| People | `GET/POST /users`, `GET/PATCH /users/{id}`, `PATCH /users/me`, `POST /users/{id}/reset-password`, `/archive`, `/unarchive` |
| Projects | `GET/POST /projects`, `GET/PATCH /projects/{id}`, `POST /projects/{id}/complete`, `/archive`, `/unarchive` |
| Milestones | `GET/POST /projects/{id}/milestones`, `GET/PATCH .../{mid}`, `POST .../{mid}/complete`, `/archive` |
| Deliverables | `GET/POST .../milestones/{mid}/deliverables`, `PATCH .../{did}`, `POST .../{did}/archive` |
| Team | `GET /projects/{id}/team`, `GET/POST .../milestones/{mid}/team`, `PATCH .../team/{uid}`, `POST .../team/{uid}/archive` |
| Costs | `GET/POST /projects/{id}/costs`, `PATCH .../{cid}`, `POST .../{cid}/archive` |
| Reports | `GET /reports/overview`, `GET /reports/my-dashboard` |
| Admin | `POST /admin/seed-demo`, `GET /health` |

Differences from the generic guide, on purpose: updates use `PATCH` (partial) rather than `PUT`; removal is `POST .../archive`
returning `200` with the archived record rather than `DELETE` returning `204`, because the requirement is "archive, never delete".

## Test it

```sh
./bin/test-backend.sh        # from the repository root: ruff, bandit, then pytest with a coverage gate
```

154 tests against a real PostgreSQL (a throwaway `pm_test` database), 97.1% coverage. "Today" is frozen to Wednesday
2026-03-11 so date maths is repeatable. See [`docs/TESTING.md`](../../docs/TESTING.md) for the full picture.

## Known limits

Labor cost uses today's salary for all worked days (a raise reprices history); public holidays are not modelled; no login
throttling yet; each Lambda container holds one database connection, so database connections equal concurrent requests
(an RDS Proxy would be the next step at high concurrency). Details and the open review findings are in `docs/CONTEXT.md`.
