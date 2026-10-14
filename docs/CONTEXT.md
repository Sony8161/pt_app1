# Project context: ACME Project Tracker

Everything a new session or teammate needs to pick this project up. Snapshot taken 2026-10-14.

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
- **Milestones are the building blocks and the unit of work.** An employee is assigned to a milestone (several
  people may share one) and works **one milestone per day**; assignments of one person never overlap.
- **No time tracking.** Every Monday-Friday inside an assignment is an 8-hour shift, so hours and cost follow from the
  calendar: working days x 8 x `salary`. Worked time counts up to today; a forecast counts the whole planned range.
- `salary` is an **hourly** rate. A milestone has a planned hours figure and budget set by the manager (business needs).
- **Nothing is ever deleted** and the API has no DELETE operations. Removing means archiving, and only admins can see
  archived records (`include_archived`). A manager **completes a milestone after ticking every deliverable**; it then
  moves to the archive (still counted in project progress). Cancelling a milestone archives it without counting it.
- Each employee has exactly one manager (already the case; a manager may have many employees).
- **Admin is a system role**, not the managers' boss in the org chart.
- **Backend first**, frontend after the API is fully working.
- Branching: `develop` (QA, LocalStack) -> `main` (prod, AWS), tags `vX.Y.Z`.
- Assumptions made (not confirmed): only employees go on milestones; employees never see money; projects a user may
  not see return 404, not 403; completing or archiving a milestone/project, or removing a person, ends their work today
  (they are free from tomorrow); a milestone needs at least one deliverable, all ticked, before it can be completed.

## What exists
| Area | State |
|---|---|
| `backend/pm-api` | Done: auth, users, projects, milestones, deliverables, milestone teams, costs, reports, demo-data. 154 tests, 97.1% coverage, no DELETE endpoints |
| `docs/postman` | Done: 138-request collection with saved example JSON, verified with Newman (554 assertions) |
| `infra/`, `bin/` | Fixed for the app (auth header, CloudFront, Aurora, secrets); `terraform validate` passes; not applied to AWS |
| LocalStack deploy | **Done**: `./bin/demo-postgres.sh` then `./bin/start-dev.sh`; Postman run passes there (138 requests, 554 assertions) |
| AWS deploy | **Not done** (`./bin/deploy-backend.sh` and `./bin/deploy-frontend.sh`) |
| `frontend/` | Demo-scale web app for all three roles (React, TypeScript, MUI), 253 tests at 99% coverage and a saved end-to-end test; see `frontend/README.md` for what is missing |
| Demo | `docs/DEMO.md`: rehearsed script; `./bin/demo-ready.sh` loads the sample company with memorable logins |
| CI workflow, backend README | Not written |

## Run it
```sh
./bin/test-backend.sh                       # lint + security scan + 154 tests (needs local Postgres)
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
- LocalStack Lambda reaches Postgres at `172.17.0.1`. The system Postgres listens on `127.0.0.1` only and changing that needs sudo, so `./bin/demo-postgres.sh` runs a Docker Postgres on that address instead.

## Known limits
- Labor cost uses today's salary for all worked days, so a raise reprices history (fix: store the rate per assignment).
- Public holidays are not modelled: every Monday-Friday is a shift.
- The old time-entry and project-assignment tables are kept as `legacy_*` (migration 002) because nothing is dropped.
- No login throttling. One shared DB connection per Lambda container (fine on Lambda, not for threaded servers).
- Aurora minimum capacity is 0.5 ACU (about $43 a month) so it never pauses.

## Next steps
1. Deploy to AWS and check `/health` and a sign-in by hand. Run the Newman collection only against a throwaway stack: it changes the admin password and creates data that can never be deleted (LocalStack is done).
2. Grow the demo frontend into the full app (profile editing, project editing, moving an employee between managers, TanStack Query, saved end-to-end tests).
3. CI workflow (pytest, vitest), backend README, branches `develop`/`main`, release tag.
