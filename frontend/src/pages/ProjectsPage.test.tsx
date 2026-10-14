import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { InternalAxiosRequestConfig } from 'axios'
import { apiError, mockRoutes, restoreApi } from '../test/mockApi'
import { project, renderPage, signIn } from '../test/pmFixtures'
import { ProjectsPage } from './ProjectsPage'

// MUI dialogs are slow to open in jsdom on a busy machine.
vi.setConfig({ testTimeout: 30_000 })

const list = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 100 })
const body = (c: InternalAxiosRequestConfig) => JSON.parse(c.data as string)

const managers = {
  items: [
    { id: 'mgr1', username: 'm1', name: 'Mia Manager', email: 'm@x.test', job_title: '', role: 'manager', manager_id: null, must_change_password: false, archived_at: null, salary: null },
    { id: 'mgr2', username: 'm2', name: 'Max Manager', email: 'x@x.test', job_title: '', role: 'manager', manager_id: null, must_change_password: false, archived_at: null, salary: null },
  ],
  total: 2,
}

afterEach(() => {
  restoreApi()
  localStorage.clear()
})

describe('Projects list', () => {
  it('shows a spinner, then one card per project', async () => {
    signIn('manager')
    mockRoutes({ 'GET /projects': list([project({ id: 'a', name: 'Alpha' }), project({ id: 'b', name: 'Beta' })]) })
    renderPage(<ProjectsPage />)
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    expect(await screen.findByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Alpha/ })).toHaveAttribute('href', '/projects/a')
  })

  it.each([
    ['admin', 'Every project in the company'],
    ['manager', 'The projects you run'],
    ['employee', 'The projects you work on'],
  ] as const)('describes the list for a %s', async (role, subtitle) => {
    signIn(role)
    mockRoutes({ 'GET /projects': list([]) })
    renderPage(<ProjectsPage />)
    expect(await screen.findByText(subtitle)).toBeInTheDocument()
  })

  it('shows an empty state when nothing matches', async () => {
    signIn('manager')
    mockRoutes({ 'GET /projects': list([]) })
    renderPage(<ProjectsPage />)
    expect(await screen.findByText('No projects match.')).toBeInTheDocument()
  })

  it('shows the error and retries', async () => {
    signIn('manager')
    let fail = true
    mockRoutes({ 'GET /projects': () => (fail ? apiError(500, 'server_error', 'Could not load projects') : list([project({ name: 'Alpha' })])) })
    renderPage(<ProjectsPage />)
    expect(await screen.findByText('Could not load projects')).toBeInTheDocument()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Alpha')).toBeInTheDocument()
  })

  it('asks the server once after typing stops, with the trimmed search text', async () => {
    signIn('manager')
    const params: Record<string, unknown>[] = []
    mockRoutes({
      'GET /projects': (c: InternalAxiosRequestConfig) => {
        params.push({ ...c.params })
        return list(c.params?.q === 'web' ? [project({ name: 'Website redesign' })] : [project({ name: 'Alpha' }), project({ id: 'b', name: 'Website redesign' })])
      },
    })
    renderPage(<ProjectsPage />)
    await screen.findByText('Alpha')
    expect(params).toEqual([{ page_size: 100 }])

    await userEvent.type(screen.getByLabelText('Search by project or manager'), ' web ')
    await waitFor(() => expect(screen.queryByText('Alpha')).not.toBeInTheDocument())
    expect(screen.getByText('Website redesign')).toBeInTheDocument()
    // one more request for the whole word, not one per letter
    expect(params).toEqual([{ page_size: 100 }, { q: 'web', page_size: 100 }])
  })

  it('filters by status', async () => {
    signIn('admin')
    const params: Record<string, unknown>[] = []
    mockRoutes({
      'GET /projects': (c: InternalAxiosRequestConfig) => {
        params.push({ ...c.params })
        return list(c.params?.status === 'completed' ? [project({ name: 'Old project', status: 'completed' })] : [project({ name: 'Alpha' })])
      },
    })
    renderPage(<ProjectsPage />)
    await screen.findByText('Alpha')
    await userEvent.click(screen.getByRole('combobox', { name: 'Status' }))
    const options = within(await screen.findByRole('listbox')).getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['All', 'Planned', 'Active', 'Completed'])
    await userEvent.click(screen.getByRole('option', { name: 'Completed' }))
    expect(await screen.findByText('Old project')).toBeInTheDocument()
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument()
    expect(params.at(-1)).toEqual({ status: 'completed', page_size: 100 })
  })

  describe('new project', () => {
    it('is offered to admins only', async () => {
      signIn('manager')
      mockRoutes({ 'GET /projects': list([]) })
      renderPage(<ProjectsPage />)
      await screen.findByText('No projects match.')
      expect(screen.queryByRole('button', { name: 'New project' })).not.toBeInTheDocument()
    })

    it('needs a name and a manager before it can be submitted', async () => {
      signIn('admin')
      mockRoutes({ 'GET /projects': list([]), 'GET /users': managers })
      renderPage(<ProjectsPage />)
      await userEvent.click(await screen.findByRole('button', { name: 'New project' }))
      const dialog = await screen.findByRole('dialog', { name: 'Create a project' })
      const submit = within(dialog).getByRole('button', { name: 'Create project' })
      expect(submit).toBeDisabled()

      await userEvent.type(within(dialog).getByLabelText(/Project name/), 'Brand refresh')
      expect(submit).toBeDisabled()
      await userEvent.click(within(dialog).getByRole('combobox', { name: /Manager/ }))
      await userEvent.click(await screen.findByRole('option', { name: 'Max Manager' }))
      expect(submit).toBeEnabled()
    })

    it('lists the managers, creates the project with snake_case fields and refreshes the list', async () => {
      signIn('admin')
      let created = false
      const sent: unknown[] = []
      const userParams: unknown[] = []
      const calls = mockRoutes({
        'GET /projects': () => list(created ? [project({ name: 'Brand refresh' })] : []),
        'GET /users': (c: InternalAxiosRequestConfig) => { userParams.push({ ...c.params }); return managers },
        'POST /projects': (c: InternalAxiosRequestConfig) => { sent.push(body(c)); created = true; return project({ name: 'Brand refresh' }) },
      })
      renderPage(<ProjectsPage />)
      await userEvent.click(await screen.findByRole('button', { name: 'New project' }))
      const dialog = await screen.findByRole('dialog', { name: 'Create a project' })

      await userEvent.type(within(dialog).getByLabelText(/Project name/), 'Brand refresh')
      await userEvent.type(within(dialog).getByLabelText('Description'), 'Logo and site')
      await userEvent.click(within(dialog).getByRole('combobox', { name: /Manager/ }))
      expect(within(await screen.findByRole('listbox')).getAllByRole('option').map((o) => o.textContent)).toEqual(['Mia Manager', 'Max Manager'])
      await userEvent.click(screen.getByRole('option', { name: 'Mia Manager' }))
      await userEvent.clear(within(dialog).getByLabelText(/^Starts/))
      await userEvent.type(within(dialog).getByLabelText(/^Starts/), '2026-11-02')
      await userEvent.clear(within(dialog).getByLabelText(/^Predicted end/))
      await userEvent.type(within(dialog).getByLabelText(/^Predicted end/), '2027-02-26')
      await userEvent.type(within(dialog).getByLabelText('Total hours'), '250')
      await userEvent.type(within(dialog).getByLabelText(/Budget/), '40000')
      await userEvent.click(within(dialog).getByRole('button', { name: 'Create project' }))

      expect(await screen.findByText('Brand refresh', { selector: 'h6' })).toBeInTheDocument()
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(userParams).toEqual([{ role: 'manager' }])
      expect(sent).toHaveLength(1)
      expect(sent[0]).toMatchObject({
        name: 'Brand refresh', description: 'Logo and site', manager_id: 'mgr1', start_date: '2026-11-02', end_date: '2027-02-26', allocated_hours: 250, budget_amount: 40000,
      })
      expect(calls.filter((c) => c === 'GET /projects').length).toBeGreaterThanOrEqual(2)
    })

    it('keeps the dialog open and shows the server reason when creating fails', async () => {
      signIn('admin')
      mockRoutes({
        'GET /projects': list([]),
        'GET /users': managers,
        'POST /projects': apiError(422, 'validation_error', 'Request validation failed', [{ field: 'end_date', message: 'end date must be after the start date' }]),
      })
      renderPage(<ProjectsPage />)
      await userEvent.click(await screen.findByRole('button', { name: 'New project' }))
      const dialog = await screen.findByRole('dialog', { name: 'Create a project' })
      await userEvent.type(within(dialog).getByLabelText(/Project name/), 'Brand refresh')
      await userEvent.click(within(dialog).getByRole('combobox', { name: /Manager/ }))
      await userEvent.click(await screen.findByRole('option', { name: 'Mia Manager' }))
      await userEvent.click(within(dialog).getByRole('button', { name: 'Create project' }))

      expect(await within(dialog).findByText('Request validation failed: end date must be after the start date')).toBeInTheDocument()
      expect(screen.getByRole('dialog', { name: 'Create a project' })).toBeInTheDocument()
      expect(within(dialog).getByLabelText(/Project name/)).toHaveValue('Brand refresh')
    })

    it('shows why the manager list is empty when it cannot be loaded, and Cancel closes the dialog', async () => {
      signIn('admin')
      mockRoutes({ 'GET /projects': list([]), 'GET /users': apiError(500, 'server_error', 'Managers unavailable') })
      renderPage(<ProjectsPage />)
      await userEvent.click(await screen.findByRole('button', { name: 'New project' }))
      const dialog = await screen.findByRole('dialog', { name: 'Create a project' })
      expect(await within(dialog).findByText('Managers unavailable')).toBeInTheDocument()
      await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    })
  })
})
