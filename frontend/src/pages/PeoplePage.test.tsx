import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthProvider'
import { apiError, mockRoutes, restoreApi } from '../test/mockApi'
import { PeoplePage } from './PeoplePage'

vi.setConfig({ testTimeout: 30_000 })

const person = (id: string, name: string, role: string, over: Record<string, unknown> = {}) => ({
  id, username: `user${id}`, name, email: `${id}@x.test`, job_title: '', role, manager_id: null,
  must_change_password: false, archived_at: null, salary: 40, ...over,
})
const admin = person('a1', 'Ada Admin', 'admin', { job_title: 'Head of delivery', salary: 90 })
const maya = person('m1', 'Maya Manager', 'manager', { job_title: 'Project manager', salary: 70 })
const eli = person('e1', 'Eli Employee', 'employee', { manager_id: 'm1', job_title: '', salary: 35.5 })
const everyone = { items: [admin, maya, eli], total: 3 }

function signIn(role: 'admin' | 'manager', id = role === 'admin' ? 'a1' : 'm1') {
  localStorage.setItem('pm.auth', JSON.stringify({
    token: 't', expiresAt: Math.floor(Date.now() / 1000) + 3600,
    user: { id, username: 'x', name: 'Me', email: 'me@x.test', jobTitle: '', role, managerId: null, mustChangePassword: false, archivedAt: null, salary: null },
  }))
}
const renderPage = () => render(<MemoryRouter><AuthProvider><PeoplePage /></AuthProvider></MemoryRouter>)
// A person's name also appears in other rows ("Reports to"), so look at the name cell only.
const rowOf = (name: string) => screen.getByText(name, { selector: 'p' }).closest('tr')!

/** Answer GET /users: managers for the dialog, the (optionally filtered) list otherwise. */
const usersRoute = (seen: Record<string, unknown>[] = []) => (config: { params?: Record<string, unknown> }) => {
  seen.push(config.params ?? {})
  if (config.params?.role === 'manager') return { items: [maya], total: 1 }
  const q = String(config.params?.q ?? '').toLowerCase()
  const items = everyone.items.filter((p) => p.name.toLowerCase().includes(q))
  return { items, total: items.length }
}

afterEach(() => {
  restoreApi()
  localStorage.clear()
  vi.useRealTimers()
})

describe('PeoplePage as an admin', () => {
  beforeEach(() => signIn('admin'))

  it('shows everyone with role, username, hourly cost and who they report to', async () => {
    mockRoutes({ 'GET /users': usersRoute() })
    renderPage()
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    await screen.findByText('Eli Employee')
    expect(screen.getByRole('columnheader', { name: 'Hourly cost' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Actions' })).toBeInTheDocument()
    const row = rowOf('Eli Employee')
    expect(within(row).getByText('employee')).toBeInTheDocument()
    expect(within(row).getByText('usere1')).toBeInTheDocument()
    expect(within(row).getByText('Maya Manager')).toBeInTheDocument() // "Reports to", found in the list
    expect(within(row).getByText('$36/h')).toBeInTheDocument()
    expect(within(row).getByText('e1@x.test')).toBeInTheDocument() // no job title: falls back to the email
    expect(within(rowOf('Maya Manager')).getByText('Project manager')).toBeInTheDocument()
    expect(within(rowOf('Maya Manager')).getByText('—')).toBeInTheDocument() // managers report to nobody
    expect(screen.getByRole('button', { name: 'New person' })).toBeInTheDocument()
  })

  it('shows a dash instead of an hourly cost the server left out', async () => {
    mockRoutes({ 'GET /users': { items: [person('e2', 'No Salary', 'employee', { salary: null })], total: 1 } })
    renderPage()
    const row = (await screen.findByText('No Salary')).closest('tr')!
    expect(within(row).getAllByText('—').length).toBeGreaterThanOrEqual(2) // reports to + hourly cost
  })

  it('finds the manager name from the managers list when a search hides the manager', async () => {
    mockRoutes({ 'GET /users': usersRoute() })
    renderPage()
    await screen.findByText('Eli Employee')
    await userEvent.type(screen.getByLabelText('Search by name, email or job title'), 'eli')
    await waitFor(() => expect(screen.queryByText('Ada Admin')).not.toBeInTheDocument(), { timeout: 3000 })
    expect(within(rowOf('Eli Employee')).getByText('Maya Manager')).toBeInTheDocument()
  })

  it('waits for a pause in typing before searching, and sends the trimmed text', async () => {
    const seen: Record<string, unknown>[] = []
    mockRoutes({ 'GET /users': usersRoute(seen) })
    renderPage()
    await screen.findByText('Eli Employee')
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const box = screen.getByLabelText('Search by name, email or job title')
    const typing = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await typing.type(box, ' ma ')
    const searches = () => seen.filter((p) => p.role === undefined)
    expect(searches().some((p) => p.q)).toBe(false) // nothing sent yet: still inside the 300 ms pause
    await vi.advanceTimersByTimeAsync(350)
    vi.useRealTimers()
    await waitFor(() => expect(searches().some((p) => p.q === 'ma')).toBe(true))
    await waitFor(() => expect(screen.queryByText('Eli Employee')).not.toBeInTheDocument())
    expect(screen.getByText('Maya Manager')).toBeInTheDocument()
  })

  it('says nobody matches when the search finds no one', async () => {
    mockRoutes({ 'GET /users': usersRoute() })
    renderPage()
    await screen.findByText('Eli Employee')
    await userEvent.type(screen.getByLabelText('Search by name, email or job title'), 'zzz')
    expect(await screen.findByText('Nobody matches.', undefined, { timeout: 3000 })).toBeInTheDocument()
  })

  it('has no New password or Archive button on the admin\'s own row', async () => {
    mockRoutes({ 'GET /users': usersRoute() })
    renderPage()
    await screen.findByText('Eli Employee')
    expect(within(rowOf('Ada Admin')).queryByRole('button')).not.toBeInTheDocument()
    expect(within(rowOf('Eli Employee')).getByRole('button', { name: 'New password' })).toBeInTheDocument()
    expect(within(rowOf('Eli Employee')).getByRole('button', { name: 'Archive' })).toBeInTheDocument()
    expect(within(rowOf('Maya Manager')).getAllByRole('button')).toHaveLength(2)
  })

  it('shows an error with a retry when the list cannot be loaded', async () => {
    let up = false
    mockRoutes({ 'GET /users': (c: { params?: Record<string, unknown> }) => (up ? usersRoute()(c) : apiError(500, 'server_error', 'The database is waking up')) })
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('The database is waking up')
    up = true
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Eli Employee')).toBeInTheDocument()
  })

  describe('New person', () => {
    const open = async () => {
      await screen.findByText('Eli Employee')
      await userEvent.click(screen.getByRole('button', { name: 'New person' }))
      return screen.findByRole('dialog', { name: 'Add a person' })
    }
    const create = () => screen.getByRole('button', { name: 'Create account' })

    it('needs a name and an email, and an employee also needs a manager', async () => {
      mockRoutes({ 'GET /users': usersRoute() })
      renderPage()
      const dialog = await open()
      expect(create()).toBeDisabled()
      await userEvent.type(within(dialog).getByLabelText(/Full name/), 'Nia New')
      expect(create()).toBeDisabled()
      await userEvent.type(within(dialog).getByLabelText(/Email/), 'nia@x.test')
      expect(create()).toBeDisabled() // role defaults to employee, so a manager is still missing
      await userEvent.click(within(dialog).getByRole('combobox', { name: /Reports to/ }))
      await userEvent.click(await screen.findByRole('option', { name: 'Maya Manager' }))
      expect(create()).toBeEnabled()
    })

    it('does not ask a manager or an admin for a manager', async () => {
      mockRoutes({ 'GET /users': usersRoute() })
      renderPage()
      const dialog = await open()
      await userEvent.type(within(dialog).getByLabelText(/Full name/), 'Nia New')
      await userEvent.type(within(dialog).getByLabelText(/Email/), 'nia@x.test')
      await userEvent.click(within(dialog).getByRole('combobox', { name: 'Role' }))
      await userEvent.click(await screen.findByRole('option', { name: 'Manager' }))
      expect(within(dialog).queryByRole('combobox', { name: /Reports to/ })).not.toBeInTheDocument()
      expect(create()).toBeEnabled()
    })

    it('creates an employee, sends the form as the API expects, and shows the generated credentials once', async () => {
      let body: Record<string, unknown> = {}
      let created = false
      const calls = mockRoutes({
        'GET /users': (c: { params?: Record<string, unknown> }) => (created && !c.params?.role ? { items: [...everyone.items, person('n1', 'Nia New', 'employee')], total: 4 } : usersRoute()(c)),
        'POST /users': (c: { data: string }) => {
          body = JSON.parse(c.data)
          created = true
          return { user: person('n1', 'Nia New', 'employee', { username: 'nn42xy' }), temporary_password: 'Tmp-Pass-777' }
        },
      })
      renderPage()
      const dialog = await open()
      await userEvent.type(within(dialog).getByLabelText(/Full name/), 'Nia New')
      await userEvent.type(within(dialog).getByLabelText(/Email/), 'nia@x.test')
      await userEvent.type(within(dialog).getByLabelText('Job title'), 'Tester')
      await userEvent.type(within(dialog).getByLabelText(/Hourly cost/), '42.5')
      await userEvent.click(within(dialog).getByRole('combobox', { name: /Reports to/ }))
      await userEvent.click(await screen.findByRole('option', { name: 'Maya Manager' }))
      await userEvent.click(create())

      const creds = await screen.findByRole('dialog', { name: 'One-time password' })
      expect(creds).toHaveTextContent('Nia New')
      expect(creds).toHaveTextContent('employee')
      expect(creds).toHaveTextContent('username nn42xy')
      expect(creds).toHaveTextContent('password Tmp-Pass-777')
      expect(body).toEqual({ name: 'Nia New', email: 'nia@x.test', job_title: 'Tester', role: 'employee', manager_id: 'm1', salary: 42.5 })
      expect(screen.queryByRole('dialog', { name: 'Add a person' })).not.toBeInTheDocument()

      await userEvent.click(within(creds).getByRole('button', { name: 'I have saved them' }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(await screen.findByText('Nia New')).toBeInTheDocument() // list reloaded
      expect(calls.filter((c) => c === 'POST /users')).toHaveLength(1)
    })

    it('sends no manager for a manager account and 0 when no hourly cost was typed', async () => {
      let body: Record<string, unknown> = {}
      mockRoutes({
        'GET /users': usersRoute(),
        'POST /users': (c: { data: string }) => {
          body = JSON.parse(c.data)
          return { user: person('n2', 'Max Mgr', 'manager'), temporary_password: 'Tmp-Pass-888' }
        },
      })
      renderPage()
      const dialog = await open()
      await userEvent.type(within(dialog).getByLabelText(/Full name/), 'Max Mgr')
      await userEvent.type(within(dialog).getByLabelText(/Email/), 'max@x.test')
      await userEvent.click(within(dialog).getByRole('combobox', { name: 'Role' }))
      await userEvent.click(await screen.findByRole('option', { name: 'Manager' }))
      await userEvent.click(create())
      expect(await screen.findByRole('dialog', { name: 'One-time password' })).toHaveTextContent('Tmp-Pass-888')
      expect(body).toMatchObject({ role: 'manager', manager_id: null, salary: 0 })
    })

    it('shows the server\'s reason in the dialog and keeps what was typed when creating fails', async () => {
      mockRoutes({
        'GET /users': usersRoute(),
        'POST /users': apiError(409, 'email_taken', 'That email is already used by another account'),
      })
      renderPage()
      const dialog = await open()
      await userEvent.type(within(dialog).getByLabelText(/Full name/), 'Nia New')
      await userEvent.type(within(dialog).getByLabelText(/Email/), 'maya@x.test')
      await userEvent.click(within(dialog).getByRole('combobox', { name: 'Role' }))
      await userEvent.click(await screen.findByRole('option', { name: 'Admin' }))
      await userEvent.click(create())
      expect(await within(dialog).findByRole('alert')).toHaveTextContent('That email is already used by another account')
      expect(within(dialog).getByLabelText(/Full name/)).toHaveValue('Nia New')
      expect(screen.queryByRole('dialog', { name: 'One-time password' })).not.toBeInTheDocument()
    })
  })

  describe('New password', () => {
    it('asks first, then shows the new one-time password for that person', async () => {
      const calls = mockRoutes({
        'GET /users': usersRoute(),
        'POST /users/:id/reset-password': { temporary_password: 'Reset-Pass-123' },
      })
      renderPage()
      await screen.findByText('Eli Employee')
      await userEvent.click(within(rowOf('Eli Employee')).getByRole('button', { name: 'New password' }))
      const confirm = await screen.findByRole('dialog', { name: 'New password for Eli Employee' })
      expect(confirm).toHaveTextContent('every open session is signed out')
      expect(calls).not.toContain('POST /users/e1/reset-password')
      await userEvent.click(within(confirm).getByRole('button', { name: 'Create new password' }))
      const creds = await screen.findByRole('dialog', { name: 'One-time password' })
      expect(creds).toHaveTextContent('Eli Employee')
      expect(creds).toHaveTextContent('username usere1')
      expect(creds).toHaveTextContent('password Reset-Pass-123')
      expect(calls).toContain('POST /users/e1/reset-password')
    })

    it('can be cancelled without changing anything', async () => {
      const calls = mockRoutes({ 'GET /users': usersRoute() })
      renderPage()
      await screen.findByText('Eli Employee')
      await userEvent.click(within(rowOf('Eli Employee')).getByRole('button', { name: 'New password' }))
      await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(calls.filter((c) => c.startsWith('POST'))).toEqual([])
    })

    it('shows the server\'s reason when the reset fails', async () => {
      mockRoutes({
        'GET /users': usersRoute(),
        'POST /users/:id/reset-password': apiError(409, 'user_archived', 'This account is archived'),
      })
      renderPage()
      await screen.findByText('Eli Employee')
      await userEvent.click(within(rowOf('Eli Employee')).getByRole('button', { name: 'New password' }))
      const confirm = await screen.findByRole('dialog')
      await userEvent.click(within(confirm).getByRole('button', { name: 'Create new password' }))
      expect(await within(confirm).findByRole('alert')).toHaveTextContent('This account is archived')
      expect(screen.queryByRole('dialog', { name: 'One-time password' })).not.toBeInTheDocument()
    })
  })

  describe('Archive', () => {
    it('asks first, then archives the person and reloads the list', async () => {
      let archived = false
      const calls = mockRoutes({
        'GET /users': (c: { params?: Record<string, unknown> }) => {
          const base = usersRoute()(c) as { items: unknown[]; total: number }
          return archived && !c.params?.role ? { items: base.items.filter((p) => (p as { id: string }).id !== 'e1'), total: 2 } : base
        },
        'POST /users/:id/archive': () => { archived = true; return person('e1', 'Eli Employee', 'employee') },
      })
      renderPage()
      await screen.findByText('Eli Employee')
      await userEvent.click(within(rowOf('Eli Employee')).getByRole('button', { name: 'Archive' }))
      const confirm = await screen.findByRole('dialog', { name: 'Archive Eli Employee?' })
      expect(confirm).toHaveTextContent('Nothing is deleted')
      expect(calls).not.toContain('POST /users/e1/archive')
      await userEvent.click(within(confirm).getByRole('button', { name: 'Archive' }))
      await waitFor(() => expect(screen.queryByText('Eli Employee')).not.toBeInTheDocument())
      expect(calls).toContain('POST /users/e1/archive')
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    })

    it('shows the server\'s reason and keeps the person when archiving is refused', async () => {
      mockRoutes({
        'GET /users': usersRoute(),
        'POST /users/:id/archive': apiError(409, 'manager_has_reports', 'Maya Manager still manages 1 person'),
      })
      renderPage()
      await screen.findByText('Maya Manager', { selector: 'p' })
      await userEvent.click(within(rowOf('Maya Manager')).getByRole('button', { name: 'Archive' }))
      const confirm = await screen.findByRole('dialog', { name: 'Archive Maya Manager?' })
      await userEvent.click(within(confirm).getByRole('button', { name: 'Archive' }))
      expect(await within(confirm).findByRole('alert')).toHaveTextContent('Maya Manager still manages 1 person')
      expect(screen.getByRole('dialog', { name: 'Archive Maya Manager?' })).toBeInTheDocument()
    })
  })
})

describe('PeoplePage as a manager', () => {
  beforeEach(() => signIn('manager'))

  it('shows the list without hourly cost, actions or the New person button', async () => {
    const seen: Record<string, unknown>[] = []
    const calls = mockRoutes({ 'GET /users': usersRoute(seen) })
    renderPage()
    await screen.findByText('Eli Employee')
    expect(screen.getByText('The people you can assign to your milestones')).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Hourly cost' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Actions' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New person' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Archive|New password/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/\/h$/)).not.toBeInTheDocument()
    expect(within(rowOf('Eli Employee')).getByText('Maya Manager')).toBeInTheDocument()
    // The managers list is only needed for the admin's dialog.
    expect(calls).toEqual(['GET /users'])
    expect(seen.some((p) => p.role === 'manager')).toBe(false)
  })

  it('shows an error when the list cannot be loaded', async () => {
    mockRoutes({ 'GET /users': apiError(403, 'forbidden', 'You may not see people') })
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('You may not see people')
  })
})
