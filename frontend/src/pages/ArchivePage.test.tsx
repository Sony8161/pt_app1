import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { InternalAxiosRequestConfig } from 'axios'
import { apiError, mockRoutes, restoreApi } from '../test/mockApi'
import { ArchivePage } from './ArchivePage'

vi.setConfig({ testTimeout: 30_000 })

const person = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id, username: `u${id}`, name, email: `${id}@x.test`, job_title: '', role: 'employee', manager_id: null,
  must_change_password: false, archived_at: null, salary: 10, ...over,
})
const project = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id, name, description: '', manager: { id: 'm1', name: 'Maya Chen' }, status: 'archived', start_date: '2026-03-02', end_date: '2026-06-26',
  allocated_hours: 100, budget_amount: 1000, completed_at: null, archived_at: null, summary: {}, ...over,
})

const projects = {
  items: [
    project('p1', 'Apollo', { archived_at: '2026-04-10T08:30:00Z' }),
    project('p2', 'Still running'),
    project('p3', 'Zeus', { archived_at: '2026-05-01T12:00:00Z' }),
  ],
  total: 3, page: 1, page_size: 100,
}
const people = {
  items: [
    person('u1', 'Ann Archived', { archived_at: '2026-02-03T10:00:00Z', role: 'manager' }),
    person('u2', 'Bo Active'),
  ],
  total: 2,
}

afterEach(() => restoreApi())

describe('ArchivePage', () => {
  it('lists only archived projects, with their manager and archive date', async () => {
    mockRoutes({ 'GET /projects': projects, 'GET /users': people })
    render(<ArchivePage />)
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    const apollo = (await screen.findByText('Apollo')).closest('tr')!
    expect(within(apollo).getByText('Maya Chen')).toBeInTheDocument()
    expect(within(apollo).getByText('Apr 10, 2026')).toBeInTheDocument()
    expect(screen.getByText('Zeus')).toBeInTheDocument()
    expect(screen.queryByText('Still running')).not.toBeInTheDocument()
  })

  it('asks the server to include archived projects and people', async () => {
    const asked: unknown[] = []
    mockRoutes({
      'GET /projects': (c: InternalAxiosRequestConfig) => { asked.push(['projects', c.params]); return projects },
      'GET /users': (c: InternalAxiosRequestConfig) => { asked.push(['users', c.params]); return people },
    })
    render(<ArchivePage />)
    await screen.findByText('Apollo')
    expect(asked).toContainEqual(['projects', { include_archived: 'true', page_size: 100 }])
    expect(asked).toContainEqual(['users', { include_archived: 'true' }])
  })

  it('says so when no project is archived', async () => {
    mockRoutes({ 'GET /projects': { ...projects, items: [project('p2', 'Still running')] }, 'GET /users': people })
    render(<ArchivePage />)
    expect(await screen.findByText('No archived projects.')).toBeInTheDocument()
  })

  it('switches to the people tab and lists only archived people', async () => {
    mockRoutes({ 'GET /projects': projects, 'GET /users': people })
    render(<ArchivePage />)
    await screen.findByText('Apollo')
    await userEvent.click(screen.getByRole('tab', { name: 'People' }))
    const ann = (await screen.findByText('Ann Archived')).closest('tr')!
    expect(within(ann).getByText('u1@x.test')).toBeInTheDocument()
    expect(within(ann).getByText('manager')).toBeInTheDocument()
    expect(within(ann).getByText('Feb 3, 2026')).toBeInTheDocument()
    expect(screen.queryByText('Bo Active')).not.toBeInTheDocument()
    expect(screen.queryByText('Apollo')).not.toBeInTheDocument()
  })

  it('says so when no person is archived', async () => {
    mockRoutes({ 'GET /projects': projects, 'GET /users': { items: [person('u2', 'Bo Active')], total: 1 } })
    render(<ArchivePage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'People' }))
    expect(await screen.findByText('No archived people.')).toBeInTheDocument()
  })

  it('restores a project and reloads the list', async () => {
    let restored = false
    const calls = mockRoutes({
      'GET /projects': () => (restored ? { ...projects, items: [projects.items[2]] } : projects),
      'GET /users': people,
      'POST /projects/:id/unarchive': () => { restored = true; return project('p1', 'Apollo') },
    })
    render(<ArchivePage />)
    const apollo = (await screen.findByText('Apollo')).closest('tr')!
    await userEvent.click(within(apollo).getByRole('button', { name: 'Restore' }))
    await vi.waitFor(() => expect(screen.queryByText('Apollo')).not.toBeInTheDocument())
    expect(calls).toContain('POST /projects/p1/unarchive')
    expect(screen.getByText('Zeus')).toBeInTheDocument()
  })

  it('restores a person and reloads the list', async () => {
    let restored = false
    const calls = mockRoutes({
      'GET /projects': projects,
      'GET /users': () => (restored ? { items: [person('u1', 'Ann Archived')], total: 1 } : people),
      'POST /users/:id/unarchive': () => { restored = true; return person('u1', 'Ann Archived') },
    })
    render(<ArchivePage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'People' }))
    const ann = (await screen.findByText('Ann Archived')).closest('tr')!
    await userEvent.click(within(ann).getByRole('button', { name: 'Restore' }))
    expect(await screen.findByText('No archived people.')).toBeInTheDocument()
    expect(calls).toContain('POST /users/u1/unarchive')
  })

  it('shows why a restore failed, keeps the row, and lets the person dismiss the message', async () => {
    mockRoutes({
      'GET /projects': projects,
      'GET /users': people,
      'POST /projects/:id/unarchive': apiError(409, 'manager_archived', 'The project manager is archived. Restore them first.'),
    })
    render(<ArchivePage />)
    const apollo = (await screen.findByText('Apollo')).closest('tr')!
    await userEvent.click(within(apollo).getByRole('button', { name: 'Restore' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The project manager is archived. Restore them first.')
    expect(screen.getByText('Apollo')).toBeInTheDocument()
    await userEvent.click(within(alert).getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('clears an old failure message when another restore is started', async () => {
    let fail = true
    mockRoutes({
      'GET /projects': projects,
      'GET /users': people,
      'POST /projects/:id/unarchive': () => (fail ? apiError(500, 'server_error', 'Something broke') : project('p1', 'Apollo')),
    })
    render(<ArchivePage />)
    const row = () => screen.getByText('Apollo').closest('tr')!
    await screen.findByText('Apollo')
    await userEvent.click(within(row()).getByRole('button', { name: 'Restore' }))
    expect(await screen.findByText('Something broke')).toBeInTheDocument()
    fail = false
    await userEvent.click(within(row()).getByRole('button', { name: 'Restore' }))
    await vi.waitFor(() => expect(screen.queryByText('Something broke')).not.toBeInTheDocument())
  })

  it('shows a readable error with a retry when the list cannot be loaded', async () => {
    let up = false
    mockRoutes({
      'GET /projects': () => (up ? projects : apiError(500, 'server_error', 'The database is waking up')),
      'GET /users': people,
    })
    render(<ArchivePage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('The database is waking up')
    up = true
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Apollo')).toBeInTheDocument()
  })
})
