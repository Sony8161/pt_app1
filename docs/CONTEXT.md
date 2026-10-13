# Project context: ACME Project Tracker

Everything a new session or teammate needs to pick this project up. Snapshot taken 2026-10-13.

## The problem
ACME runs many projects across departments but cannot see status, resource allocation, deadlines or budget.
The app must answer: which projects are at risk, how resources are allocated, who is over-allocated, deliverables
and their status, dependency between deliverables (milestones), and budget consumed versus planned.

## Stakeholder requirements (not stored anywhere else in the repo)
- **Stack:** FastAPI (Python) preferably on AWS Lambda; React (TypeScript recommended) with Material UI and
  react-responsive; PostgreSQL; Terraform; shell scripts for deploying locally and to AWS; QA/prod version control.
- **Three roles**
  - *Admin*: full control. Creates projects (for a manager), users and admins, moves an employee to another manager,
    archives. Never hard-deletes: everything is archived.
  - *Manager*: assigns employees to projects, edits their own projects and milestones, adjusts the budget, edits
    employees on their immediate team, says when a project is done. Cannot create or delete projects. Exactly one
    manager per project.
  - *Employee*: sees only the project(s) they are assigned to, edits only their own name and email, has one manager.
- **Users:** name, generated password, generated 6-character username, email, job title, hourly cost (called `salary`).
- **Projects:** start and predicted end date, allocated hours, budget; milestones with start/due dates and hours;
  non-labor costs (technology and so on); track employee cost and total project cost. Typical week is 40 hours.

## Decisions taken with the user
- Everything is driven by **start and end dates** (schedule progress, risk, planned to active).
- An employee gives **one project their full 8-hour day**. They may be on several projects over time, but their
  assignments (date ranges) never overlap, and they log at most 8 hours a day.
- `salary` is an **hourly** rate. Labor cost = hours x salary.
- **Admin is a system role**, not the managers' boss in the org chart.
- **Backend first**, frontend after the API is fully working.
- Branching: `develop` (QA, LocalStack) -> `main` (prod, AWS), tags `vX.Y.Z`.
- Assumptions made (not confirmed): only employees go on teams; employees never see money; projects a user may not
  see return 404, not 403; completing or archiving a project ends its assignments today.

## What exists
| Area | State |
|---|---|
| `backend/pm-api` | Done: auth, users, projects, milestones, team, time, costs, reports, demo-data. 120 tests, 96% coverage |
| `docs/postman` | Done: 126-request collection with saved example JSON, verified with Newman (502 assertions) |
| `infra/`, `bin/` | Fixed for the app (auth header, CloudFront, Aurora, secrets); `terraform validate` passes; not applied |
| LocalStack / AWS deploy | **Not done**: needs `sudo` to rebind Postgres, run `./bin/start-dev.sh` |
| `frontend/` | **Not started** (still the Vite hello-world) |
| CI workflow, backend README | Not written |

## Run it
```sh
./bin/test-backend.sh                       # lint + security scan + 120 tests (needs local Postgres)
cd backend/pm-api && source .venv/bin/activate
POSTGRES_NAME=pm_dev uvicorn app.main:app --port 8000   # then open http://localhost:8000/docs
# first login: admin1 / ChangeMe123!  (you must change it); POST /admin/seed-demo loads sample data
npx newman run docs/postman/acme-pm-api.postman_collection.json -e docs/postman/local.postman_environment.json
```

## Platform gotchas found along the way
- `bin/proxy-server.js` used to drop the `Authorization` header (fixed).
- CloudFront forwards `/api/pm-api/*` unstripped, the local proxy strips it; the app handles both.
- `pip` on the VDI belongs to Python 3.14 but Lambda runs 3.13; use `python3 -m pip` (fixed in `start-dev.sh`).
- The old CloudFront rule turning every 404 into `index.html` would hide API errors (removed).
- Root `.gitignore` ignores any directory named `lib`, `assets`, `build`, `dist`, `coverage`, `tmp`.
- LocalStack Lambda reaches Postgres at `172.17.0.1`, so Postgres must listen on `0.0.0.0` (`start-dev.sh` does it).

## Known limits
- Labor cost uses today's salary for all hours, so a raise reprices history (fix: store the rate per time entry).
- No login throttling. One shared DB connection per Lambda container (fine on Lambda, not for threaded servers).
- Aurora minimum capacity is 0.5 ACU (about $43 a month) so it never pauses.

## Next steps
1. Deploy to LocalStack with `./bin/start-dev.sh`, then to AWS; re-run the Newman collection against each.
2. Frontend (React + TypeScript + MUI) against the finished API.
3. CI workflow (pytest, vitest), backend README, branches `develop`/`main`, release tag.
