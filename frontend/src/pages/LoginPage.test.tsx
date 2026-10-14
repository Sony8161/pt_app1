import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthProvider'
import { mockApi, restoreApi } from '../test/mockApi'
import { RequireAuth, RequireRole } from '../auth/guards'
import { LoginPage } from './LoginPage'

const user = (role: string, mustChangePassword = false) => ({
  id: '1', username: 'ab12cd', name: 'Alex Kim', email: 'a@x.test', job_title: '', role, manager_id: null,
  must_change_password: mustChangePassword, archived_at: null, salary: null,
})


function renderApp(path = '/login') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/change-password" element={<p>Choose a new password</p>} />
          <Route element={<RequireAuth />}>
            <Route path="/my-work" element={<p>My work page</p>} />
            <Route path="/people" element={<RequireRole roles={['admin', 'manager']}><p>People page</p></RequireRole>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  restoreApi()
  localStorage.clear()
})

describe('sign in', () => {
  it('shows the server sentence when the password is wrong', async () => {
    mockApi(401, { error: { code: 'invalid_credentials', message: 'Invalid username or password' } })
    renderApp()
    await userEvent.type(screen.getByLabelText(/username/i), 'ab12cd')
    await userEvent.type(screen.getByLabelText(/password/i), 'nope')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Invalid username or password')).toBeInTheDocument()
  })

  it('sends an employee to their own page after signing in', async () => {
    mockApi(200, { access_token: 't', expires_at: Math.floor(Date.now() / 1000) + 3600, user: user('employee') })
    renderApp()
    await userEvent.type(screen.getByLabelText(/username/i), 'ab12cd')
    await userEvent.type(screen.getByLabelText(/password/i), 'Secret123')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('My work page')).toBeInTheDocument()
  })

  it('forces a new password before anything else when the account has a one-time password', async () => {
    mockApi(200, { access_token: 't', expires_at: Math.floor(Date.now() / 1000) + 3600, user: user('manager', true) })
    renderApp()
    await userEvent.type(screen.getByLabelText(/username/i), 'ab12cd')
    await userEvent.type(screen.getByLabelText(/password/i), 'OneTime123')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Choose a new password')).toBeInTheDocument()
  })
})

describe('role guard', () => {
  it('sends an employee who opens a manager page back to their own page', async () => {
    localStorage.setItem('pm.auth', JSON.stringify({ token: 't', expiresAt: Math.floor(Date.now() / 1000) + 3600, user: { ...user('employee'), mustChangePassword: false } }))
    renderApp('/people')
    await waitFor(() => expect(screen.getByText('My work page')).toBeInTheDocument())
    expect(screen.queryByText('People page')).not.toBeInTheDocument()
  })

  it('sends a signed-out visitor to the sign-in page', async () => {
    renderApp('/people')
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })
})
