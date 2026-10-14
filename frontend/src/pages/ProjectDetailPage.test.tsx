import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { InternalAxiosRequestConfig } from 'axios'
import { apiError, mockRoutes, restoreApi } from '../test/mockApi'
import { employeeProject, milestone, project, renderPage, signIn } from '../test/pmFixtures'
import { ProjectDetailPage } from './ProjectDetailPage'

// MUI dialogs are slow to open in jsdom on a busy machine.
vi.setConfig({ testTimeout: 30_000 })

const body = (c: InternalAxiosRequestConfig) => JSON.parse(c.data as string)
const milestones = (items: unknown[]) => ({ items, total: items.length, planned_hours: 100, planned_budget: 8000 })
const team = (laborCost: number | null = 2400) => ({
  items: [
    { assignment_id: 'a1', user_id: 'u1', name: 'Ann Designer', job_title: 'Designer', milestone_id: 'm1', milestone_name: 'Design', start_date: '2026-09-01', end_date: '2026-09-30', days_worked: 10, hours_worked: 80, labor_cost: laborCost === null ? null : 2400 },
  ],
  total: 1, hours_worked: 80, labor_cost: laborCost,
})
const costs = {
  items: [{ id: 'c1', category: 'license', description: 'Figma seats', amount: 900, incurred_on: '2026-09-15' }],
  total: 1, other_cost: 900, labor_cost: 2400, total_cost: 3300, budget_amount: 50000, budget_remaining: 46700,
}

/** Default answers for everything a project page asks for; `extra` replaces or adds routes. */
function serve(p: unknown = project(), extra: Record<string, unknown> = {}) {
  return mockRoutes({
    'GET /projects/:id': p,
    'GET /projects/:id/milestones': milestones([milestone()]),
    'GET /projects/:id/milestones/:id/deliverables': { items: [], total: 0, done: 0, ready_to_complete: false },
    'GET /projects/:id/milestones/:id/team': { items: [], total: 0, hours_worked: 0, labor_cost: 0 },
    'GET /projects/:id/team': team(),
    'GET /projects/:id/costs': costs,
    ...extra,
  })
}

const page = () => renderPage(<ProjectDetailPage />, '/projects/p1', '/projects/:projectId')

afterEach(() => {
  restoreApi()
  localStorage.clear()
})

describe('Project detail: what everyone sees', () => {
  it('shows a spinner, then the header, description and summary tiles', async () => {
    signIn('manager', { id: 'someone-else' })
    serve()
    page()
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Website redesign' })).toBeInTheDocument()
    expect(screen.getByText(/Mia Manager · Sep 1, 2026 to Dec 31, 2026/)).toBeInTheDocument()
    expect(screen.getByText('New public site')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('On track')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /All projects/ })).toHaveAttribute('href', '/projects')

    const tile = (label: string) => screen.getByText(label, { selector: 'p' }).parentElement as HTMLElement
    expect(tile('Time')).toHaveTextContent('60 days left40% of the calendar used')
    expect(tile('Milestones')).toHaveTextContent('1 of 4none past due')
    expect(tile('Hours')).toHaveTextContent('120 h of 500 h3 people on milestones')
    expect(tile('Budget')).toHaveTextContent('$15,000 of $50,000Forecast $50,000')
    expect(screen.getByRole('img', { name: 'Work done 25 percent, calendar elapsed 40 percent' })).toBeInTheDocument()
  })

  it('counts days late and past-due milestones when the project is behind', async () => {
    signIn('manager', { id: 'someone-else' })
    serve(project({}, { days_remaining: -5, milestones_overdue: 2 }))
    page()
    await screen.findByRole('heading', { name: 'Website redesign' })
    expect(screen.getByText('5 days late')).toBeInTheDocument()
    expect(screen.getByText('2 past due')).toBeInTheDocument()
  })

  it('lists the reasons in a box when the project is at risk', async () => {
    signIn('manager', { id: 'someone-else' })
    serve(project({}, { risk_level: 'at_risk', risk_reasons: ['Hours are running ahead of progress', 'One milestone is due this week'] }))
    page()
    expect(await screen.findByText('Why this project is at risk')).toBeInTheDocument()
    const box = screen.getByRole('alert')
    expect(within(box).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Hours are running ahead of progress', 'One milestone is due this week',
    ])
    expect(screen.getByText('At risk')).toBeInTheDocument()
  })

  it('words the reasons box as overdue when the project is overdue', async () => {
    signIn('manager', { id: 'someone-else' })
    serve(project({}, { risk_level: 'overdue', risk_reasons: ['The end date has passed'] }))
    page()
    expect(await screen.findByText('Why this project is overdue')).toBeInTheDocument()
  })

  it('has no reasons box when the project is on track', async () => {
    signIn('manager', { id: 'someone-else' })
    serve()
    page()
    await screen.findByRole('heading', { name: 'Website redesign' })
    expect(screen.queryByText(/Why this project is/)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the server sentence when the project cannot be loaded, and retries', async () => {
    signIn('manager')
    let found = false
    serve(undefined, { 'GET /projects/:id': () => (found ? project() : apiError(404, 'not_found', 'Project not found')) })
    page()
    expect(await screen.findByText('Project not found')).toBeInTheDocument()
    found = true
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Website redesign' })).toBeInTheDocument()
  })

  it('shows the milestones tab first, with an empty state and a separate error for the milestone list', async () => {
    signIn('manager', { id: 'someone-else' })
    serve(project(), { 'GET /projects/:id/milestones': milestones([]) })
    page()
    expect(await screen.findByText(/No milestones yet/)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Milestones' })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps the page and shows an error when only the milestone list fails', async () => {
    signIn('manager', { id: 'someone-else' })
    serve(project(), { 'GET /projects/:id/milestones': apiError(500, 'server_error', 'Milestones are unavailable') })
    page()
    expect(await screen.findByText('Milestones are unavailable')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Website redesign' })).toBeInTheDocument()
  })

  it('renders one card per milestone', async () => {
    signIn('manager', { id: 'someone-else' })
    serve(project(), { 'GET /projects/:id/milestones': milestones([milestone(), milestone({ id: 'm2', name: 'Build' })]) })
    page()
    expect(await screen.findByRole('heading', { name: 'Design' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Build' })).toBeInTheDocument()
  })

  it('shows who works on the project in the Team tab', async () => {
    signIn('manager', { id: 'someone-else' })
    serve()
    page()
    await userEvent.click(await screen.findByRole('tab', { name: 'Team' }))
    expect(await screen.findByText('Ann Designer')).toBeInTheDocument()
    const row = screen.getByText('Ann Designer').closest('tr') as HTMLElement
    expect(row).toHaveTextContent('Designer')
    expect(row).toHaveTextContent('Design')
    expect(row).toHaveTextContent('Sep 1, 2026 to Sep 30, 2026')
    expect(row).toHaveTextContent('80 h')
    expect(row).toHaveTextContent('$2,400')
    expect(screen.getByText('Total').closest('tr')).toHaveTextContent('80 h$2,400')
  })

  it('says nobody is assigned when the team is empty', async () => {
    signIn('manager', { id: 'someone-else' })
    serve(project(), { 'GET /projects/:id/team': { items: [], total: 0, hours_worked: 0, labor_cost: 0 } })
    page()
    await userEvent.click(await screen.findByRole('tab', { name: 'Team' }))
    expect(await screen.findByText('Nobody is assigned to a milestone yet.')).toBeInTheDocument()
    expect(screen.queryByText('Total')).not.toBeInTheDocument()
  })

  it('shows an error with retry when the team cannot be loaded', async () => {
    signIn('manager', { id: 'someone-else' })
    let fail = true
    serve(project(), { 'GET /projects/:id/team': () => (fail ? apiError(500, 'server_error', 'Team unavailable') : team()) })
    page()
    await userEvent.click(await screen.findByRole('tab', { name: 'Team' }))
    expect(await screen.findByText('Team unavailable')).toBeInTheDocument()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Ann Designer')).toBeInTheDocument()
  })
})

describe('Project detail: employee', () => {
  beforeEach(() => signIn('employee'))

  it('sees no Costs tab, no Budget tile and no money anywhere', async () => {
    serve(employeeProject(), {
      'GET /projects/:id/milestones': milestones([milestone({ budget_amount: null, labor_cost: null, budget_pct: null })]),
      'GET /projects/:id/team': team(null),
    })
    const { container } = page()
    await screen.findByRole('heading', { name: 'Website redesign' })
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Milestones', 'Team'])
    expect(screen.queryByText('Budget', { selector: 'p' })).not.toBeInTheDocument()
    await screen.findByText('Planned')
    expect(container.textContent).not.toContain('$')

    await userEvent.click(screen.getByRole('tab', { name: 'Team' }))
    await screen.findByText('Ann Designer')
    expect(screen.queryByText('Cost so far')).not.toBeInTheDocument()
    expect(container.textContent).not.toContain('$')
  })

  it('has no manager or admin buttons, even on an active project', async () => {
    const calls = serve(employeeProject())
    page()
    await screen.findByRole('heading', { name: 'Website redesign' })
    for (const name of ['Mark project complete', 'Archive', 'Add milestone', 'Assign a person', 'Complete milestone']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
    expect(calls.some((c) => c.startsWith('POST'))).toBe(false)
  })
})

describe('Project detail: who can manage', () => {
  it('lets the project manager complete an active project, then refreshes', async () => {
    signIn('manager', { id: 'manager-1' })
    let status = 'active'
    const calls = serve(undefined, {
      'GET /projects/:id': () => project({ status }, status === 'completed' ? { risk_level: 'done' } : {}),
      'POST /projects/:id/complete': () => { status = 'completed'; return project({ status }) },
    })
    page()
    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: 'Mark project complete' }))
    const dialog = await screen.findByRole('dialog', { name: 'Mark this project complete?' })
    expect(dialog).toHaveTextContent('can no longer be edited')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Mark complete' }))

    expect(await screen.findByText('Completed')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Mark project complete' })).not.toBeInTheDocument())
    expect(calls).toContain('POST /projects/p1/complete')
    // a finished project can no longer be edited
    expect(screen.queryByRole('button', { name: 'Add milestone' })).not.toBeInTheDocument()
  })

  it('shows the server refusal inside the dialog when completing fails', async () => {
    signIn('manager', { id: 'manager-1' })
    serve(undefined, { 'POST /projects/:id/complete': apiError(409, 'open_milestones', 'Finish or cancel the open milestones first') })
    page()
    await userEvent.click(await screen.findByRole('button', { name: 'Mark project complete' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Mark complete' }))
    expect(await within(dialog).findByText('Finish or cancel the open milestones first')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('gives another manager no buttons for a project they do not run', async () => {
    signIn('manager', { id: 'someone-else' })
    serve()
    page()
    await screen.findByRole('heading', { name: 'Website redesign' })
    expect(screen.queryByRole('button', { name: 'Mark project complete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add milestone' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
  })

  it('lets an admin archive a project after confirming', async () => {
    signIn('admin')
    const calls = serve(undefined, { 'POST /projects/:id/archive': project({ status: 'archived' }) })
    page()
    await userEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    const dialog = await screen.findByRole('dialog', { name: 'Archive this project?' })
    expect(dialog).toHaveTextContent('nothing is deleted')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Archive' }))
    await waitFor(() => expect(calls).toContain('POST /projects/p1/archive'))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('does not archive when the admin cancels', async () => {
    signIn('admin')
    const calls = serve()
    page()
    await userEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(calls.some((c) => c.startsWith('POST'))).toBe(false)
  })

  it('asks for archived milestones only when an admin is looking', async () => {
    const seen: unknown[] = []
    const handler = (c: InternalAxiosRequestConfig) => { seen.push(c.params?.include_archived); return milestones([]) }
    signIn('admin')
    serve(undefined, { 'GET /projects/:id/milestones': handler })
    page()
    await screen.findByText(/No milestones yet/)
    expect(seen).toEqual(['true'])
    restoreApi()
    localStorage.clear()
    document.body.innerHTML = ''

    seen.length = 0
    signIn('manager', { id: 'manager-1' })
    serve(undefined, { 'GET /projects/:id/milestones': handler })
    page()
    await screen.findAllByText(/No milestones yet/)
    expect(seen).toEqual([undefined])
  })

  it('hides archive and manage buttons on an archived project', async () => {
    signIn('admin')
    serve(project({ status: 'archived' }))
    page()
    await screen.findByText('Archived')
    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add milestone' })).not.toBeInTheDocument()
  })
})

describe('Project detail: add a milestone', () => {
  const open = async () => {
    await userEvent.click(await screen.findByRole('button', { name: 'Add milestone' }))
    return screen.findByRole('dialog', { name: 'Add a milestone' })
  }

  it('needs a name, then posts the milestone in snake_case and reloads the list', async () => {
    signIn('manager', { id: 'manager-1' })
    let added = false
    const sent: unknown[] = []
    const calls = serve(undefined, {
      'GET /projects/:id/milestones': () => milestones(added ? [milestone({ name: 'Research' })] : []),
      'POST /projects/:id/milestones': (c: InternalAxiosRequestConfig) => { sent.push(body(c)); added = true; return milestone({ name: 'Research' }) },
    })
    page()
    const dialog = await open()
    expect(dialog).toHaveTextContent('Dates, hours and budget must fit inside the project (Sep 1, 2026 to Dec 31, 2026).')
    const submit = within(dialog).getByRole('button', { name: 'Add milestone' })
    expect(submit).toBeDisabled()

    await userEvent.type(within(dialog).getByLabelText(/^Name/), 'Research')
    await userEvent.type(within(dialog).getByLabelText(/What is this milestone for/), 'Interviews')
    await userEvent.clear(within(dialog).getByLabelText(/^Starts/))
    await userEvent.type(within(dialog).getByLabelText(/^Starts/), '2026-10-05')
    await userEvent.clear(within(dialog).getByLabelText(/^Due/))
    await userEvent.type(within(dialog).getByLabelText(/^Due/), '2026-11-15')
    await userEvent.type(within(dialog).getByLabelText('Planned hours'), '60')
    await userEvent.type(within(dialog).getByLabelText(/Budget/), '5000')
    expect(submit).toBeEnabled()
    await userEvent.click(submit)

    expect(await screen.findByRole('heading', { name: 'Research' })).toBeInTheDocument()
    expect(sent).toHaveLength(1)
    expect(sent[0]).toMatchObject({ name: 'Research', description: 'Interviews', start_date: '2026-10-05', due_date: '2026-11-15', allocated_hours: 60, budget_amount: 5000 })
    expect(calls.filter((c) => c === 'GET /projects/p1')).toHaveLength(2)
  })

  it('shows the server reason in the dialog and keeps what was typed', async () => {
    signIn('manager', { id: 'manager-1' })
    serve(undefined, {
      'POST /projects/:id/milestones': apiError(422, 'validation_error', 'Request validation failed', [{ field: 'due_date', message: 'due date is outside the project' }]),
    })
    page()
    const dialog = await open()
    await userEvent.type(within(dialog).getByLabelText(/^Name/), 'Research')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add milestone' }))
    expect(await within(dialog).findByText('Request validation failed: due date is outside the project')).toBeInTheDocument()
    expect(within(dialog).getByLabelText(/^Name/)).toHaveValue('Research')
  })
})

describe('Project detail: costs tab', () => {
  const openCosts = async () => {
    await userEvent.click(await screen.findByRole('tab', { name: 'Costs' }))
    await screen.findByText('People (labor)')
  }

  it('shows the totals and each recorded cost', async () => {
    signIn('manager', { id: 'someone-else' })
    serve()
    page()
    await openCosts()
    const total = (label: string) => screen.getByText(label).parentElement as HTMLElement
    expect(total('People (labor)')).toHaveTextContent('$2,400')
    expect(total('Other costs')).toHaveTextContent('$900')
    expect(total('Total spent')).toHaveTextContent('$3,300')
    expect(total('Budget left')).toHaveTextContent('$46,700')
    const row = screen.getByText('Figma seats').closest('tr') as HTMLElement
    expect(row).toHaveTextContent('Sep 15, 2026')
    expect(row).toHaveTextContent('license')
    expect(row).toHaveTextContent('$900')
    expect(screen.queryByRole('button', { name: 'Add a cost' })).not.toBeInTheDocument()
  })

  it('says so when no other costs were recorded', async () => {
    signIn('manager', { id: 'someone-else' })
    serve(project(), { 'GET /projects/:id/costs': { ...costs, items: [], total: 0 } })
    page()
    await openCosts()
    expect(screen.getByText('No other costs recorded.')).toBeInTheDocument()
  })

  it('shows an error when the costs cannot be loaded', async () => {
    signIn('manager', { id: 'someone-else' })
    serve(project(), { 'GET /projects/:id/costs': apiError(500, 'server_error', 'Costs unavailable') })
    page()
    await userEvent.click(await screen.findByRole('tab', { name: 'Costs' }))
    expect(await screen.findByText('Costs unavailable')).toBeInTheDocument()
  })

  it('adds a cost with its category, then refreshes both the costs and the project totals', async () => {
    signIn('manager', { id: 'manager-1' })
    const sent: unknown[] = []
    let added = false
    const calls = serve(undefined, {
      'GET /projects/:id/costs': () => (added ? { ...costs, items: [...costs.items, { id: 'c2', category: 'travel', description: 'Client visit', amount: 450, incurred_on: '2026-10-01' }] } : costs),
      'POST /projects/:id/costs': (c: InternalAxiosRequestConfig) => { sent.push(body(c)); added = true; return {} },
    })
    page()
    await openCosts()
    await userEvent.click(screen.getByRole('button', { name: 'Add a cost' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add a cost' })
    const submit = within(dialog).getByRole('button', { name: 'Add cost' })
    expect(submit).toBeDisabled()

    await userEvent.click(within(dialog).getByRole('combobox', { name: 'Category' }))
    await userEvent.click(await screen.findByRole('option', { name: 'travel' }))
    await userEvent.type(within(dialog).getByLabelText(/What was it for/), 'Client visit')
    expect(submit).toBeDisabled()
    await userEvent.type(within(dialog).getByLabelText(/Amount/), '450')
    await userEvent.clear(within(dialog).getByLabelText(/^Date/))
    await userEvent.type(within(dialog).getByLabelText(/^Date/), '2026-10-01')
    expect(submit).toBeEnabled()
    await userEvent.click(submit)

    expect(await screen.findByText('Client visit')).toBeInTheDocument()
    expect(sent).toEqual([expect.objectContaining({ category: 'travel', description: 'Client visit', amount: 450 })])
    expect(sent[0]).toHaveProperty('incurred_on', '2026-10-01')
    expect(calls.filter((c) => c === 'GET /projects/p1')).toHaveLength(2)
  })

  it('shows the refusal in the dialog when the cost is rejected', async () => {
    signIn('admin')
    serve(undefined, { 'POST /projects/:id/costs': apiError(409, 'project_closed', 'This project is closed') })
    page()
    await openCosts()
    await userEvent.click(screen.getByRole('button', { name: 'Add a cost' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add a cost' })
    await userEvent.type(within(dialog).getByLabelText(/What was it for/), 'Server')
    await userEvent.type(within(dialog).getByLabelText(/Amount/), '10')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add cost' }))
    expect(await within(dialog).findByText('This project is closed')).toBeInTheDocument()
  })
})
