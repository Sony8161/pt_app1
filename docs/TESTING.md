# Testing: commands, results and known gaps

Everything below was run on 2026-10-14 against the code in this repository. "Where" says what each test needs.
The structure follows the Testing Expectations in [full-stack.md](./full-stack.md).

## Summary

| Layer | What | Command | Result |
|---|---|---|---|
| Backend unit + integration + error tests | Business rules against a **real PostgreSQL** | `./bin/test-backend.sh` | **154 tests pass**, 97.1% coverage (gate 80%) |
| Backend lint and security | `ruff` and `bandit` (same scan as CI) | `./bin/test-backend.sh` | clean |
| Frontend component + API integration tests | React Testing Library with the API mocked | `cd frontend && npm run test:coverage` | **253 tests pass**, 99.2% statements, 98.1% branches (gate 80%) |
| Frontend static checks | ESLint, TypeScript, production build, `npm audit` | `npm run lint && npm run typecheck && npm run build && npm audit` | clean, 0 vulnerabilities |
| End-to-end | The demo journey through browser, proxy, Lambda and PostgreSQL, plus accessibility scans | `cd frontend && npm run e2e` | **17 of 17 checks pass** (11 journey, 6 axe scans) |
| API contract | 138 requests with 554 assertions (Postman/Newman) | `npx newman run docs/postman/acme-pm-api.postman_collection.json -e docs/postman/localstack.postman_environment.json` | 0 failures, locally and on LocalStack |
| Performance | Artillery load test | `npx artillery run docs/load/artillery.yml` | see Load test below |

## Backend

```sh
./bin/test-backend.sh                  # ruff, bandit (tracked files, like CI), pytest with a coverage gate
./bin/test-backend.sh -k reports       # any pytest arguments are passed on
```

Needs a local PostgreSQL (`postgres` / `postgres123` on `localhost:5432`); tests create and use a throwaway `pm_test` database
and skip themselves if PostgreSQL is not reachable. "Today" is frozen to Wednesday 2026-03-11 so date maths is repeatable.

| The guide asks for | What covers it |
|---|---|
| Unit tests of functions in isolation | `test_metrics.py` (risk rules), `test_security.py` (passwords, tokens), `test_workdays.py` (Monday-Friday maths), `test_db_transactions.py` (commit and rollback) |
| Integration tests with a real database | one file per domain: auth, users, projects, milestones, deliverables, team, costs, reports, admin seed |
| Error handling and validation tests | every domain has refusal cases (400, 401, 403, 404, 409); `test_error_handling.py` covers the 409, 503 and 500 safety nets and the single error shape |
| Role rules and privilege escalation | role matrix in each domain's tests: a manager cannot change role or salary, an admin cannot change their own role, hidden things are 404, an employee never receives money |
| "Archive, never delete" | `test_no_deletes.py` asserts the API has no DELETE operation and that archived records are admin-only |
| Observability | `test_observability.py`: one access-log line per request, request id returned, tokens and search text never logged |

Coverage: 97.1% overall. All nine router files and `app/core/errors.py` (the error handlers) are at 100%. The lowest files are
`app/main.py` (94%, the health check's database-down branch) and `app/domains/users/service.py` (95%).

## Frontend

```sh
cd frontend
npm test                    # run once
npm run test:coverage       # with the 80% gate (statements, branches, functions, lines)
npm run lint && npm run typecheck && npm run build
```

253 tests in 28 files, using Vitest and React Testing Library (the guide names Jest; Vitest is the same API on Vite). The API is
mocked at the axios adapter (`src/test/mockApi.ts`), so tests exercise the real client code: key conversion, error mapping, the
401 handler. Covered: every page, the dialogs (busy, error and success states), role differences (employees see no money, no manager
buttons), route guards and redirects, the sliding session refresh, and the forced password change.
Excluded from the coverage figure: `main.tsx` (wiring) and `theme.ts` (colours).

## End-to-end and accessibility

```sh
./bin/demo-postgres.sh && ./bin/start-dev.sh     # the stack, in its own terminal
./bin/demo-ready.sh                              # sample company and logins
cd frontend && npm run e2e                       # SHOTS=/some/dir saves a screenshot per step
./bin/demo-ready.sh                              # the test completes a milestone and archives a project, so reset
```

17 checks drive a real browser through: sign-in, the dashboard ranking, an employee with no money visible, a manager seeing only
their own projects, a refused double booking, a refused then accepted milestone sign-off, the forced first-login password change,
an admin seeing the archived milestone, and archive then restore. Six pages are scanned with axe-core (sign-in, dashboard,
project detail, my work, a manager's project page, people); the test fails on any serious or critical issue. The first run found
one (a tooltip put an `aria-label` on a plain element); it is fixed and now guarded.

## Load test

```sh
./bin/demo-ready.sh
npx artillery run docs/load/artillery.yml                 # realistic: 5 new users a second, about 30 requests a second
npx artillery run docs/load/artillery.yml -e stress       # finds the limit; see the warning below
```

Read-only traffic as a manager: overview, project list, one project, its milestones, people, health. Run on LocalStack on a
2-CPU, 8 GB cloud desktop with the API warm.

| Profile | Requests | Failed | Median | p95 | p99 | Max |
|---|---|---|---|---|---|---|
| Realistic (up to 5 users/s, about 23 requests/s observed) | 1,440 | **0** | 16 ms | 23 ms | 34 ms | 51 ms |
| Stress (ramp to 15 users/s, about 90 requests/s offered) | 2,554 | 1,769 (HTTP 500 x1,228, 502 x96, timeouts x445) | 1.7 s | 5.1 s | 6.7 s | 7.9 s |

What the stress run means:
- The 500s are **not application errors**. LocalStack's own log says `Could not start new environment ... OSError(24, 'Too many open files')`:
  the emulator ran out of file handles while starting about 40 Lambda containers on a 2-CPU machine.
- It does show the design's scaling rule: every concurrent request gets its own Lambda container, and each container holds one
  database connection. 41 containers meant 39 open connections. On AWS the same rule applies (see the scalability plan in the
  presentation document: RDS Proxy and reserved concurrency).
- After a stress run LocalStack keeps replaying queued requests and recreating containers for several minutes. Wait for the container count
  (`docker ps | grep -c lambda`) to settle, remove them, and run `./bin/demo-ready.sh` before presenting.
- These figures say how the emulator copes on this machine, not how AWS behaves. Run the same file against a test stack on AWS
  (`-e` and `--target`) before quoting capacity.

## Manual validation

Walked through by hand and by the end-to-end script: UI to API to PostgreSQL for each role, on a laptop-width and a phone-width window.
The backup screenshots are in `docs/demo-screenshots/`.

## Logs and monitoring

Each request writes one JSON line (`method`, `path`, `status`, `ms`, `request_id`) and returns an `X-Request-Id` header.

```sh
# LocalStack
AWS_ENDPOINT_URL="http://localhost.localstack.cloud:4566" aws logs tail /aws/lambda/coding-workshop-pm-api-<app code> --follow --format short
# AWS
aws logs tail /aws/lambda/coding-workshop-pm-api-<app code> --follow --format short
curl http://localhost:3001/api/pm-api/health      # {"status":"ok","database":"ok",...}; 503 when the database is down
```

## Known gaps

- **Not run on AWS.** The Terraform validates but has not been applied, so the cloud path (CloudFront routing, Aurora over SSL, the
  generated secrets) is untested. The Postman collection and the load test are ready to run against a throwaway stack.
- **Load numbers are from an emulator** on a small machine, as explained above. No test measures database load or Aurora scaling.
- **The CI workflow has not run on GitHub yet** (`.github/workflows/ci.yml`); the same commands pass locally.
- **No automated test for concurrent assignment**: the row lock that stops two managers booking the same person at once has no test
  with two real connections, so deleting it would not fail a test. Listed in the review findings.
- **Frontend tests mock the API**; only the end-to-end script runs the real stack, and it covers the demo journey, not every screen
  (editing a project, moving an employee between managers and costs are not driven end to end).
- **Open code-review findings** (about 22 lesser items, listed in the presentation document, section 17), including no login throttling.
