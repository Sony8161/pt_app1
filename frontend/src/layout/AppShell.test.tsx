import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthProvider'
import { AppShell } from './AppShell'

let wide = true
vi.mock('react-responsive', () => ({ useMediaQuery: () => wide }))

const sessionFor = (role: string) => ({
  token: 't', expiresAt: Math.floor(Date.now() / 1000) + 3600,
  user: { id: '1', username: 'ab12cd', name: 'Alex Kim', email: 'a@x.test', jobTitle: '', role, managerId: null, mustChangePassword: false, archivedAt: null, salary: null },
})

function renderShell(role: string | null, path = '/dashboard') {
  if (role) localStorage.setItem('pm.auth', JSON.stringify(sessionFor(role)))
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<p>dashboard content</p>} />
            <Route path="/projects/:id" element={<p>project content</p>} />
            <Route path="/projects" element={<p>projects content</p>} />
            <Route path="/people" element={<p>people content</p>} />
            <Route path="/archive" element={<p>archive content</p>} />
            <Route path="/my-work" element={<p>my work content</p>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => { wide = true })
afterEach(() => localStorage.clear())

describe('AppShell on a wide screen', () => {
  it('shows a side menu with the manager items and marks the open one', () => {
    renderShell('manager', '/people')
    const menu = screen.getByRole('navigation', { name: 'Main' })
    const links = within(menu).getAllByRole('link').map((l) => l.textContent)
    expect(links).toEqual(['Dashboard', 'Projects', 'People'])
    expect(within(menu).getByRole('link', { name: 'People' })).toHaveClass('Mui-selected')
    expect(within(menu).getByRole('link', { name: 'Dashboard' })).not.toHaveClass('Mui-selected')
    expect(screen.getByText('people content')).toBeInTheDocument()
  })

  it('adds the Archive item for an admin only', () => {
    renderShell('admin')
    expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Archive' })).toHaveAttribute('href', '/archive')
  })

  it('keeps Projects highlighted on a project detail page', () => {
    renderShell('manager', '/projects/abc')
    expect(screen.getByRole('link', { name: 'Projects' })).toHaveClass('Mui-selected')
  })

  it('shows the person, their role and the page content', () => {
    renderShell('manager')
    expect(screen.getByText('Alex Kim')).toBeInTheDocument()
    expect(screen.getByText('manager')).toBeInTheDocument()
    expect(screen.getByText('dashboard content')).toBeInTheDocument()
  })

  it('moves between pages through the menu', async () => {
    renderShell('manager')
    await userEvent.click(screen.getByRole('link', { name: 'Projects' }))
    expect(await screen.findByText('projects content')).toBeInTheDocument()
  })

  it('shows an employee a single item', () => {
    renderShell('employee', '/my-work')
    const menu = screen.getByRole('navigation', { name: 'Main' })
    expect(within(menu).getAllByRole('link')).toHaveLength(1)
    expect(within(menu).getByRole('link', { name: 'My work' })).toBeInTheDocument()
  })

  it('signs out and clears the saved session', async () => {
    renderShell('manager')
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(localStorage.getItem('pm.auth')).toBeNull()
    // With nobody signed in the frame draws nothing.
    expect(screen.queryByText('dashboard content')).not.toBeInTheDocument()
  })

  it('draws nothing when nobody is signed in', () => {
    const { container } = renderShell(null)
    expect(container).toBeEmptyDOMElement()
  })

  it('has no bottom bar', () => {
    renderShell('manager')
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    expect(document.querySelector('.MuiBottomNavigation-root')).toBeNull()
  })
})

describe('AppShell on a narrow screen', () => {
  beforeEach(() => { wide = false })

  it('uses a bottom bar instead of the side menu, and hides the name to save room', () => {
    renderShell('manager', '/people')
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument()
    const bar = document.querySelector('.MuiBottomNavigation-root') as HTMLElement
    expect(within(bar).getAllByRole('link').map((l) => l.textContent)).toEqual(['Dashboard', 'Projects', 'People'])
    expect(within(bar).getByRole('link', { name: 'People' })).toHaveClass('Mui-selected')
    expect(screen.queryByText('Alex Kim')).not.toBeInTheDocument()
    expect(screen.getByText('people content')).toBeInTheDocument()
  })

  it('does not show a bottom bar when there is only one place to go', () => {
    renderShell('employee', '/my-work')
    expect(document.querySelector('.MuiBottomNavigation-root')).toBeNull()
    expect(screen.getByText('my work content')).toBeInTheDocument()
  })

  it('still lets the person sign out', async () => {
    renderShell('admin')
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(localStorage.getItem('pm.auth')).toBeNull()
  })
})
