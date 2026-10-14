import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { apiError, mockRoutes, restoreApi } from '../test/mockApi'
import { employeeProject, renderPage, signIn } from '../test/pmFixtures'
import { MyWorkPage } from './MyWorkPage'

const ref = { project_id: 'p1', project_name: 'Website redesign', milestone_id: 'm1', milestone_name: 'Design', start_date: '2026-10-01', end_date: '2026-10-30' }
const mine = (overrides: Record<string, unknown> = {}) => ({
  project_id: 'p1', project_name: 'Website redesign', milestone_id: 'm1', milestone_name: 'Design', status: 'in_progress',
  start_date: '2026-10-05', end_date: '2026-10-20', due_date: '2026-10-31', deliverables_total: 4, deliverables_done: 1, ...overrides,
})
const dashboard = (overrides: Record<string, unknown> = {}) => ({
  as_of: '2026-10-13', current_work: ref, my_milestones: [mine()], projects: [employeeProject()],
  hours_today: 8, hours_this_week: 24, week_capacity: 40, ...overrides,
})

beforeEach(() => signIn('employee', { name: 'Robin Hood' }))
afterEach(() => {
  restoreApi()
  localStorage.clear()
})

describe('My work', () => {
  it('greets the person by first name and shows what they work on today', async () => {
    mockRoutes({ 'GET /reports/my-dashboard': dashboard() })
    renderPage(<MyWorkPage />)
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Hello, Robin' })).toBeInTheDocument()
    expect(screen.getByText('Your work, Oct 13, 2026')).toBeInTheDocument()
    expect(screen.getByText('Today')).toBeInTheDocument()
    expect(screen.getByText(/Website redesign · you are on this until Oct 30, 2026/)).toBeInTheDocument()
  })

  it('shows the weekly hours as a progress bar', async () => {
    mockRoutes({ 'GET /reports/my-dashboard': dashboard() })
    renderPage(<MyWorkPage />)
    await screen.findByText('Hours this week')
    expect(screen.getByText('24 of 40')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Hours this week' })).toHaveAttribute('aria-valuenow', '60')
  })

  it('caps the weekly bar at 100 percent when the person is over capacity', async () => {
    mockRoutes({ 'GET /reports/my-dashboard': dashboard({ hours_this_week: 48 }) })
    renderPage(<MyWorkPage />)
    await screen.findByText('48 of 40')
    expect(screen.getByRole('progressbar', { name: 'Hours this week' })).toHaveAttribute('aria-valuenow', '100')
  })

  it('says the person is free when they are not on a milestone today', async () => {
    mockRoutes({ 'GET /reports/my-dashboard': dashboard({ current_work: null }) })
    renderPage(<MyWorkPage />)
    expect(await screen.findByText('You are not on a milestone today.')).toBeInTheDocument()
    expect(screen.queryByText(/you are on this until/)).not.toBeInTheDocument()
  })

  it('shows each milestone with its deliverables progress and a link to the project', async () => {
    mockRoutes({
      'GET /reports/my-dashboard': dashboard({
        my_milestones: [mine(), mine({ milestone_id: 'm2', milestone_name: 'Launch', project_id: 'p2', project_name: 'Mobile app', deliverables_total: 0, deliverables_done: 0 })],
      }),
    })
    renderPage(<MyWorkPage />)
    await screen.findByText('My milestones')
    const design = screen.getByText(/1 of 4 deliverables done/).closest('.MuiPaper-root') as HTMLElement
    expect(within(design).getByText('Design')).toBeInTheDocument()
    expect(within(design).getByText('1 of 4 deliverables done')).toBeInTheDocument()
    expect(within(design).getByRole('progressbar', { name: 'Deliverables done' })).toHaveAttribute('aria-valuenow', '25')
    expect(within(design).getByRole('link')).toHaveAttribute('href', '/projects/p1')
    expect(within(design).getByRole('link')).toHaveTextContent('Website redesign · you work on it Oct 5, 2026 to Oct 20, 2026')

    const launch = screen.getByText('Launch').closest('.MuiPaper-root') as HTMLElement
    expect(within(launch).getByText('0 of 0 deliverables done')).toBeInTheDocument()
    expect(within(launch).getByRole('progressbar', { name: 'Deliverables done' })).toHaveAttribute('aria-valuenow', '0')
  })

  it('shows an empty state when nothing is assigned, and no projects section', async () => {
    mockRoutes({ 'GET /reports/my-dashboard': dashboard({ current_work: null, my_milestones: [], projects: [] }) })
    renderPage(<MyWorkPage />)
    expect(await screen.findByText('Nothing is assigned to you yet.')).toBeInTheDocument()
    expect(screen.queryByText('My projects')).not.toBeInTheDocument()
  })

  it('never shows money anywhere on the page', async () => {
    mockRoutes({ 'GET /reports/my-dashboard': dashboard() })
    const { container } = renderPage(<MyWorkPage />)
    await screen.findByText('My projects')
    expect(container.textContent).not.toMatch(/\$/)
    expect(screen.queryByText('Spent')).not.toBeInTheDocument()
    expect(screen.queryByText('Budget used')).not.toBeInTheDocument()
    // the project card still shows the non-money facts
    expect(screen.getByText('Milestones')).toBeInTheDocument()
  })

  it('shows the error and reloads on retry', async () => {
    let fail = true
    mockRoutes({ 'GET /reports/my-dashboard': () => (fail ? apiError(500, 'server_error', 'Try later') : dashboard()) })
    renderPage(<MyWorkPage />)
    expect(await screen.findByText('Try later')).toBeInTheDocument()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Hello, Robin' })).toBeInTheDocument()
  })
})
