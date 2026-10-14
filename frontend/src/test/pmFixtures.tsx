import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthProvider'

type Role = 'admin' | 'manager' | 'employee'

/** A signed-in person as saved in localStorage (camelCase, like the app keeps it). */
export function signIn(role: Role, overrides: Record<string, unknown> = {}) {
  const user = {
    id: `${role}-1`, username: 'ab12cd', name: 'Alex Kim', email: 'a@x.test', jobTitle: '', role, managerId: null,
    mustChangePassword: false, archivedAt: null, salary: null, ...overrides,
  }
  localStorage.setItem('pm.auth', JSON.stringify({ token: 't', expiresAt: Math.floor(Date.now() / 1000) + 3600, user }))
  return user
}

/** Render a page inside a router (at `path`, matching `route`) and the real AuthProvider. */
export function renderPage(ui: ReactElement, path = '/', route = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path={route} element={ui} />
          <Route path="/projects/:projectId" element={<p>Project page</p>} />
          <Route path="/projects" element={<p>Projects list</p>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

/** API bodies in snake_case, like the real server sends them. */
export function summary(overrides: Record<string, unknown> = {}) {
  return {
    days_total: 100, days_elapsed: 40, days_remaining: 60, schedule_pct: 40,
    hours_worked: 120, hours_remaining: 380, hours_pct: 24,
    milestones_total: 4, milestones_done: 1, milestones_overdue: 0, milestones_pct: 25,
    team_size: 3, risk_level: 'on_track', risk_reasons: [],
    labor_cost: 12000, forecast_cost: 50000, other_cost: 3000, total_cost: 15000, budget_remaining: 35000, budget_pct: 30,
    ...overrides,
  }
}

export function project(overrides: Record<string, unknown> = {}, summaryOverrides: Record<string, unknown> = {}) {
  return {
    id: 'p1', name: 'Website redesign', description: 'New public site', manager: { id: 'manager-1', name: 'Mia Manager' },
    status: 'active', start_date: '2026-09-01', end_date: '2026-12-31', allocated_hours: 500, budget_amount: 50000,
    completed_at: null, archived_at: null, summary: summary(summaryOverrides), ...overrides,
  }
}

/** The same project as an employee gets it: every money field is null. */
export function employeeProject(overrides: Record<string, unknown> = {}) {
  return project({ budget_amount: null, ...overrides }, {
    labor_cost: null, forecast_cost: null, other_cost: null, total_cost: null, budget_remaining: null, budget_pct: null,
  })
}

export function milestone(overrides: Record<string, unknown> = {}) {
  return {
    id: 'm1', project_id: 'p1', name: 'Design', description: 'Wireframes and mockups', start_date: '2026-09-01', due_date: '2026-10-31',
    status: 'in_progress', is_overdue: false, allocated_hours: 100, hours_worked: 40, budget_amount: 8000, labor_cost: 3200, budget_pct: 40,
    assignees: 1, deliverables_total: 2, deliverables_done: 1, completed_at: null, review_note: '', archived_at: null, ...overrides,
  }
}

export function deliverable(overrides: Record<string, unknown> = {}) {
  return { id: 'd1', milestone_id: 'm1', name: 'Wireframes', description: '', done: false, done_at: null, ...overrides }
}
