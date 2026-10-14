# ACME Project Tracker: frontend

React + TypeScript + Material UI single-page app for the `pm-api` backend. One app, three roles: the menu and
the pages each person sees follow their role, and the server enforces the same rules.

| Role | Opens to | Can do |
|---|---|---|
| Admin | Dashboard | Everything: create projects and people, archive and restore, load sample data |
| Manager | Dashboard | Run their projects: milestones, deliverables, team, costs, completion |
| Employee | My work | See their milestone, hours this week and deliverables. No money is ever shown |

## Run it

```sh
cd frontend && npm install
# 1. start the API (see ../backend/pm-api): POSTGRES_NAME=pm_dev uvicorn app.main:app --port 8000
# 2. start the site; /api/pm-api is forwarded to the API, so no CORS setup is needed
npm run dev          # http://localhost:3000
```

First sign-in: `admin1` / `ChangeMe123!` (you must choose a new password), then **Load sample data** on the
dashboard. It creates two managers, six employees and four projects and shows their one-time passwords once.

`VITE_API_URL` (empty by default) is the address of the API when it is not on the same host as the site.
`VITE_PROXY_TARGET` changes where `npm run dev` forwards API calls (default `http://127.0.0.1:8000`).
`./bin/start-dev.sh` and `./bin/deploy-frontend.sh` set these for LocalStack and AWS.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server on port 3000 |
| `npm run build` | Type check, then production build into `dist/` |
| `npm test` | Vitest and React Testing Library: 253 tests across the API client, every page and dialog, role guards, session refresh |
| `npm run test:coverage` | The same with an 80% gate on statements, branches, functions and lines (currently 99% / 98%) |
| `npm run e2e` | Playwright through the real stack (see `docs/TESTING.md`): the demo journey for all three roles plus axe accessibility scans |
| `npm run lint` | ESLint (TypeScript, React hooks rules) |

## Layout

```
src/
  api/         client.ts (one axios instance with interceptors: token, error shape, 401), case.ts (snake_case <-> camelCase),
               types.ts (response shapes), useApi.ts (load data for a screen)
  auth/        AuthProvider (token + user, kept in localStorage), route guards
  layout/      AppShell: side menu on a laptop, bottom tab bar on a phone (react-responsive)
  components/  PulseBar (the signature progress bar), RiskChip, ProjectCard, MilestoneCard,
               FormDialog (every "fill in and confirm" action), CredentialsDialog, Async
  pages/       Login, ChangePassword, Dashboard, Projects, ProjectDetail (+Team, Costs), People, Archive, MyWork
```

## Design rules

- One question per screen. Colour means status only (green on track, amber at risk, red overdue, grey done).
- The **pulse bar** shows work done (the fill) against the calendar (the dark marker): fill short of the marker means behind.
- Plain words, a confirmation that says what will happen before anything is archived or completed, and every server error shown as the sentence the server wrote.
- Phone first: the menu becomes a bottom bar, forms stack.

## Known limits (demo scope)

- Data is loaded with a small `useApi` hook. A production version would add a cache (TanStack Query) and, for the
  project page, one endpoint that returns milestones with their checklists instead of one request per milestone.
- Not built yet: editing your own profile, editing a project's fields, moving an employee to another manager,
  restoring archived milestones, pagination controls.
