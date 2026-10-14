import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { apiError, mockNoAnswer, mockRoutes, restoreApi } from '../test/mockApi'
import { project, renderPage, signIn } from '../test/pmFixtures'
import { DashboardPage } from './DashboardPage'

const work = (name: string, milestone: string) => ({
  project_id: 'p1', project_name: name, milestone_id: 'm1', milestone_name: milestone, start_date: '2026-10-01', end_date: '2026-10-30',
})

const overview = (overrides: Record<string, unknown> = {}) => ({
  as_of: '2026-10-13',
  counts: { projects: 2, planned: 0, active: 2, completed: 0, on_track: 0, at_risk: 1, overdue: 1 },
  totals: { budget: 150000, spent: 60000, labor_cost: 50000, other_cost: 10000, budget_remaining: 90000, forecast_cost: 120000, hours_allocated: 900, hours_worked: 300 },
  projects: [
    project({ id: 'p9', name: 'Mobile app' }, { risk_level: 'overdue', risk_reasons: ['2 milestones are past due'] }),
    project({ id: 'p1', name: 'Website redesign' }, { risk_level: 'at_risk', risk_reasons: ['Hours are running ahead'] }),
  ],
  allocation: [
    { user_id: 'u1', name: 'Ann Busy', job_title: 'Designer', manager_name: 'Mia', state: 'allocated', current_work: work('Website redesign', 'Wireframes'), next_work: null, hours_this_week: 32, week_capacity: 40 },
    { user_id: 'u2', name: 'Ben Free', job_title: 'Developer', manager_name: 'Mia', state: 'available', current_work: null, next_work: work('Mobile app', 'Build'), hours_this_week: 0, week_capacity: 40 },
    { user_id: 'u3', name: 'Cy Idle', job_title: 'Tester', manager_name: null, state: 'available', current_work: null, next_work: null, hours_this_week: 0, week_capacity: 40 },
  ],
  available_people: 2,
  ...overrides,
})

const empty = () => overview({
  counts: { projects: 0, planned: 0, active: 0, completed: 0, on_track: 0, at_risk: 0, overdue: 0 },
  projects: [], allocation: [], available_people: 0,
})

afterEach(() => {
  restoreApi()
  localStorage.clear()
})

describe('Dashboard', () => {
  it('shows a spinner while loading, then the headline numbers', async () => {
    signIn('manager')
    mockRoutes({ 'GET /reports/overview': overview() })
    renderPage(<DashboardPage />)
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByText(/Where every project stands today, Oct 13, 2026/)).toBeInTheDocument()

    expect(screen.getByText('Need attention').parentElement).toHaveTextContent('21 overdue, 1 at risk')
    expect(screen.getByText('Active projects').parentElement).toHaveTextContent('20 planned, 0 completed')
    expect(screen.getByText('Spent so far').parentElement).toHaveTextContent('$60,000of $150,000 budget')
    expect(screen.getByText('People free').parentElement).toHaveTextContent('2not on a milestone today')
  })

  it('lists the projects in the order the server sends them (most urgent first)', async () => {
    signIn('manager')
    mockRoutes({ 'GET /reports/overview': overview() })
    renderPage(<DashboardPage />)
    await screen.findByText('Projects, most urgent first')
    const links = screen.getAllByRole('link').filter((l) => l.getAttribute('href')?.startsWith('/projects/'))
    const cards = links.filter((l) => /Mobile app|Website redesign/.test(l.textContent ?? '') && l.querySelector('h6'))
    expect(cards.map((c) => c.querySelector('h6')?.textContent)).toEqual(['Mobile app', 'Website redesign'])
    expect(cards[0]).toHaveTextContent('2 milestones are past due')
    expect(cards[0]).toHaveAttribute('href', '/projects/p9')
  })

  it('shows who is busy and who is free, with what each person works on next', async () => {
    signIn('admin')
    mockRoutes({ 'GET /reports/overview': overview() })
    renderPage(<DashboardPage />)
    await screen.findByText('Who is busy and who is free')
    const row = (name: string) => screen.getByText(name).closest('tr') as HTMLElement

    expect(within(row('Ann Busy')).getByText('Busy')).toBeInTheDocument()
    expect(within(row('Ann Busy')).getByRole('link')).toHaveTextContent('Wireframes · Website redesign')
    expect(row('Ann Busy')).toHaveTextContent('32 of 40 h')
    expect(within(row('Ben Free')).getByText('Free')).toBeInTheDocument()
    expect(row('Ben Free')).toHaveTextContent('Next: Build from Oct 1, 2026')
    expect(row('Cy Idle')).toHaveTextContent('Nothing planned')
  })

  it('says so when there are no employees', async () => {
    signIn('manager')
    mockRoutes({ 'GET /reports/overview': overview({ allocation: [] }) })
    renderPage(<DashboardPage />)
    expect(await screen.findByText('No employees yet.')).toBeInTheDocument()
  })

  it('does not offer sample data when there are projects', async () => {
    signIn('admin')
    mockRoutes({ 'GET /reports/overview': overview() })
    renderPage(<DashboardPage />)
    await screen.findByText('Projects, most urgent first')
    expect(screen.queryByRole('button', { name: 'Load sample data' })).not.toBeInTheDocument()
  })

  it('shows the error with a retry that loads the page', async () => {
    signIn('manager')
    let fail = true
    const calls = mockRoutes({
      'GET /reports/overview': () => (fail ? apiError(500, 'server_error', 'The database is waking up') : overview()),
    })
    renderPage(<DashboardPage />)
    expect(await screen.findByText('The database is waking up')).toBeInTheDocument()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.queryByText('The database is waking up')).not.toBeInTheDocument()
    expect(calls).toEqual(['GET /reports/overview', 'GET /reports/overview'])
  })

  it('tells the person when the server cannot be reached', async () => {
    signIn('manager')
    mockNoAnswer()
    renderPage(<DashboardPage />)
    expect(await screen.findByText(/Cannot reach the server/)).toBeInTheDocument()
  })

  describe('with no projects', () => {
    it('tells an employee or manager that nothing is assigned, without a sample-data button', async () => {
      signIn('employee')
      mockRoutes({ 'GET /reports/overview': empty() })
      renderPage(<DashboardPage />)
      expect(await screen.findByText('No projects are assigned to you yet.')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Load sample data' })).not.toBeInTheDocument()
    })

    it('lets an admin load sample data and shows the one-time passwords', async () => {
      signIn('admin')
      let seeded = false
      const calls = mockRoutes({
        'GET /reports/overview': () => (seeded ? overview() : empty()),
        'POST /admin/seed-demo': () => {
          seeded = true
          return {
            created: true, message: 'ok',
            accounts: [
              { name: 'Mia Manager', role: 'manager', username: 'mia01', temporary_password: 'Temp-Pass-1' },
              { name: 'Ben Free', role: 'employee', username: 'ben02', temporary_password: 'Temp-Pass-2' },
            ],
          }
        },
      })
      renderPage(<DashboardPage />)
      await userEvent.click(await screen.findByRole('button', { name: 'Load sample data' }))

      const dialog = await screen.findByRole('dialog', { name: 'Sample accounts created' })
      expect(dialog).toHaveTextContent('Mia Manager · manager')
      expect(dialog).toHaveTextContent('username mia01 password Temp-Pass-1')
      expect(dialog).toHaveTextContent('username ben02 password Temp-Pass-2')
      // the dashboard behind it was reloaded and now shows the new projects
      expect(calls).toContain('POST /admin/seed-demo')
      expect(calls.filter((c) => c === 'GET /reports/overview')).toHaveLength(2)
      expect(await screen.findByText('Projects, most urgent first')).toBeInTheDocument()
      expect(screen.queryByText(/There are no projects yet/)).not.toBeInTheDocument()

      await userEvent.click(within(dialog).getByRole('button', { name: 'I have saved them' }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    })

    it('shows the "already exists" message and no credentials when sample data was loaded before', async () => {
      signIn('admin')
      mockRoutes({
        'GET /reports/overview': empty(),
        'POST /admin/seed-demo': { created: false, message: 'Sample data already exists', accounts: [] },
      })
      renderPage(<DashboardPage />)
      await userEvent.click(await screen.findByRole('button', { name: 'Load sample data' }))
      expect(await screen.findByText('Sample data already exists')).toBeInTheDocument()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('shows the server error when loading sample data fails', async () => {
      signIn('admin')
      mockRoutes({
        'GET /reports/overview': empty(),
        'POST /admin/seed-demo': apiError(403, 'forbidden', 'Only admins can do this'),
      })
      renderPage(<DashboardPage />)
      await userEvent.click(await screen.findByRole('button', { name: 'Load sample data' }))
      expect(await screen.findByText('Only admins can do this')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Load sample data' })).toBeEnabled()
    })
  })
})
