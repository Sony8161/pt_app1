import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { App } from './App'
import { AuthProvider } from './auth/AuthProvider'

vi.mock('react-responsive', () => ({ useMediaQuery: () => true }))
// The pages are lazy-loaded; stand-ins keep these tests about routing only.
vi.mock('./pages/ArchivePage', () => ({ ArchivePage: () => <p>archive page</p> }))
vi.mock('./pages/DashboardPage', () => ({ DashboardPage: () => <p>dashboard page</p> }))
vi.mock('./pages/MyWorkPage', () => ({ MyWorkPage: () => <p>my work page</p> }))
vi.mock('./pages/PeoplePage', () => ({ PeoplePage: () => <p>people page</p> }))
vi.mock('./pages/ProjectDetailPage', () => ({ ProjectDetailPage: () => <p>project detail page</p> }))
vi.mock('./pages/ProjectsPage', () => ({ ProjectsPage: () => <p>projects page</p> }))

function signIn(role: string, mustChangePassword = false) {
  localStorage.setItem('pm.auth', JSON.stringify({
    token: 't', expiresAt: Math.floor(Date.now() / 1000) + 3600,
    user: { id: '1', username: 'ab12cd', name: 'Alex Kim', email: 'a@x.test', jobTitle: '', role, managerId: null, mustChangePassword, archivedAt: null, salary: null },
  }))
}

const renderAt = (path: string) =>
  render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>)

afterEach(() => localStorage.clear())

describe('App routing', () => {
  it('sends a signed-out visitor to the sign-in page', async () => {
    renderAt('/projects')
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByText('projects page')).not.toBeInTheDocument()
  })

  it('sends a signed-out visitor on an unknown address to the sign-in page', async () => {
    renderAt('/no/such/page')
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows the sign-in page at /login', async () => {
    renderAt('/login')
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('opens an employee on their own work, inside the app frame', async () => {
    signIn('employee')
    renderAt('/my-work')
    expect(await screen.findByText('my work page')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
  })

  it.each(['manager', 'admin'])('opens a %s on the dashboard', async (role) => {
    signIn(role)
    renderAt('/dashboard')
    expect(await screen.findByText('dashboard page')).toBeInTheDocument()
  })

  it('sends an employee who opens the dashboard, people or archive back to their own page', async () => {
    signIn('employee')
    for (const path of ['/dashboard', '/people', '/archive']) {
      const { unmount } = renderAt(path)
      expect(await screen.findByText('my work page')).toBeInTheDocument()
      expect(screen.queryByText(/dashboard page|people page|archive page/)).not.toBeInTheDocument()
      unmount()
    }
  })

  it('sends a manager who opens the archive to the dashboard and a manager who opens my-work too', async () => {
    signIn('manager')
    const { unmount } = renderAt('/archive')
    expect(await screen.findByText('dashboard page')).toBeInTheDocument()
    unmount()
    renderAt('/my-work')
    expect(await screen.findByText('dashboard page')).toBeInTheDocument()
  })

  it('lets a manager open people and an admin open the archive', async () => {
    signIn('manager')
    const { unmount } = renderAt('/people')
    expect(await screen.findByText('people page')).toBeInTheDocument()
    unmount()
    signIn('admin')
    renderAt('/archive')
    expect(await screen.findByText('archive page')).toBeInTheDocument()
  })

  it('opens the project list and a project page for everyone signed in', async () => {
    signIn('employee')
    const { unmount } = renderAt('/projects')
    expect(await screen.findByText('projects page')).toBeInTheDocument()
    unmount()
    renderAt('/projects/abc')
    expect(await screen.findByText('project detail page')).toBeInTheDocument()
  })

  it('sends a signed-in user on an unknown address to their home page', async () => {
    signIn('employee')
    const { unmount } = renderAt('/nonsense')
    expect(await screen.findByText('my work page')).toBeInTheDocument()
    unmount()
    signIn('manager')
    renderAt('/nonsense')
    expect(await screen.findByText('dashboard page')).toBeInTheDocument()
  })

  it('makes someone with a one-time password choose a new one before any page', async () => {
    signIn('manager', true)
    renderAt('/dashboard')
    expect(await screen.findByRole('heading', { name: 'Choose a new password' })).toBeInTheDocument()
    expect(screen.queryByText('dashboard page')).not.toBeInTheDocument()
  })
})
