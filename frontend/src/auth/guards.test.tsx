import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider } from './AuthProvider'
import { RequireAuth, RequireRole } from './guards'

const user = (role: string, mustChangePassword = false) => ({
  id: '1', username: 'ab12cd', name: 'Alex Kim', email: 'a@x.test', jobTitle: '', role, managerId: null,
  mustChangePassword, archivedAt: null, salary: null,
})
const signIn = (role: string, mustChangePassword = false) =>
  localStorage.setItem('pm.auth', JSON.stringify({ token: 't', expiresAt: Math.floor(Date.now() / 1000) + 3600, user: user(role, mustChangePassword) }))

function Where() {
  const { pathname, state } = useLocation()
  return <p>{`at ${pathname}${state && (state as { from?: string }).from ? ` from ${(state as { from: string }).from}` : ''}`}</p>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Where />} />
          <Route path="/change-password" element={<Where />} />
          <Route path="/my-work" element={<Where />} />
          <Route path="/dashboard" element={<Where />} />
          <Route element={<RequireAuth />}>
            <Route path="/secret" element={<p>secret page</p>} />
            <Route path="/admin-only" element={<RequireRole roles={['admin']}><p>admin page</p></RequireRole>} />
            <Route path="/staff" element={<RequireRole roles={['admin', 'manager']}><p>staff page</p></RequireRole>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => localStorage.clear())

describe('RequireAuth', () => {
  it('sends a signed-out visitor to the sign-in page and remembers where they wanted to go', () => {
    renderAt('/secret')
    expect(screen.getByText('at /login from /secret')).toBeInTheDocument()
    expect(screen.queryByText('secret page')).not.toBeInTheDocument()
  })

  it('sends someone with a one-time password to choose a new one before anything else', () => {
    signIn('manager', true)
    renderAt('/secret')
    expect(screen.getByText('at /change-password')).toBeInTheDocument()
    expect(screen.queryByText('secret page')).not.toBeInTheDocument()
  })

  it('lets a signed-in user through', () => {
    signIn('employee')
    renderAt('/secret')
    expect(screen.getByText('secret page')).toBeInTheDocument()
  })
})

describe('RequireRole', () => {
  it('shows the page to a role that is allowed', () => {
    signIn('manager')
    renderAt('/staff')
    expect(screen.getByText('staff page')).toBeInTheDocument()
  })

  it('sends an employee to their own page', () => {
    signIn('employee')
    renderAt('/staff')
    expect(screen.getByText('at /my-work')).toBeInTheDocument()
    expect(screen.queryByText('staff page')).not.toBeInTheDocument()
  })

  it('sends a manager who opens an admin page to the dashboard', () => {
    signIn('manager')
    renderAt('/admin-only')
    expect(screen.getByText('at /dashboard')).toBeInTheDocument()
    expect(screen.queryByText('admin page')).not.toBeInTheDocument()
  })

  it('lets an admin into an admin page', () => {
    signIn('admin')
    renderAt('/admin-only')
    expect(screen.getByText('admin page')).toBeInTheDocument()
  })

  it('shows nothing at all when used without a signed-in user', () => {
    const { container } = render(
      <MemoryRouter>
        <AuthProvider><RequireRole roles={['admin']}><p>admin page</p></RequireRole></AuthProvider>
      </MemoryRouter>,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
