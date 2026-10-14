import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { InternalAxiosRequestConfig } from 'axios'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthProvider'
import { http } from '../api/client'
import { apiError, mockRoutes, restoreApi } from '../test/mockApi'
import { ChangePasswordPage } from './ChangePasswordPage'

// The machine running the suite can be slow; typing into MUI fields character by character adds up.
vi.setConfig({ testTimeout: 30_000 })

const apiUser = (role: string, mustChangePassword: boolean) => ({
  id: '1', username: 'ab12cd', name: 'Alex Kim', email: 'a@x.test', job_title: '', role, manager_id: null,
  must_change_password: mustChangePassword, archived_at: null, salary: null,
})
const FUTURE = () => Math.floor(Date.now() / 1000) + 3600

function signIn(role: string, mustChangePassword = true) {
  const { job_title, manager_id, must_change_password, archived_at, ...rest } = apiUser(role, mustChangePassword)
  localStorage.setItem('pm.auth', JSON.stringify({
    token: 'old', expiresAt: FUTURE(),
    user: { ...rest, jobTitle: job_title, managerId: manager_id, mustChangePassword: must_change_password, archivedAt: archived_at },
  }))
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/change-password']}>
      <AuthProvider>
        <Routes>
          <Route path="/change-password" element={<ChangePasswordPage />} />
          <Route path="/login" element={<p>sign in page</p>} />
          <Route path="/my-work" element={<p>my work page</p>} />
          <Route path="/dashboard" element={<p>dashboard page</p>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

const save = () => screen.getByRole('button', { name: 'Save new password' })
async function fill(current: string, next: string, confirm: string) {
  await userEvent.type(screen.getByLabelText(/Current password/), current)
  await userEvent.type(screen.getByLabelText(/^New password/), next)
  await userEvent.type(screen.getByLabelText(/Repeat new password/), confirm)
}

afterEach(() => {
  restoreApi()
  localStorage.clear()
})

describe('ChangePasswordPage', () => {
  it('sends a signed-out visitor to the sign-in page', () => {
    renderPage()
    expect(screen.getByText('sign in page')).toBeInTheDocument()
  })

  it('explains the one-time password when the account must change it', () => {
    signIn('employee', true)
    renderPage()
    expect(screen.getByText(/Your one-time password only works once/)).toBeInTheDocument()
    expect(screen.getByText(/at least 8 characters/)).toBeInTheDocument()
  })

  it('does not mention a one-time password when the person chose to change theirs', () => {
    signIn('employee', false)
    renderPage()
    expect(screen.queryByText(/one-time password/)).not.toBeInTheDocument()
  })

  it('keeps Save disabled until all three fields are filled and the two new passwords match', async () => {
    signIn('employee')
    renderPage()
    expect(save()).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Current password/), 'OneTime123')
    await userEvent.type(screen.getByLabelText(/^New password/), 'Brand-New-9')
    expect(save()).toBeDisabled() // not repeated yet
    await userEvent.type(screen.getByLabelText(/Repeat new password/), 'Brand-New-9')
    expect(save()).toBeEnabled()
  })

  it('says so when the repeated password does not match, and clears the message when it does', async () => {
    signIn('employee')
    renderPage()
    await userEvent.type(screen.getByLabelText(/^New password/), 'Brand-New-9')
    expect(screen.queryByText('The two passwords do not match')).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText(/Repeat new password/), 'Brand-New-8')
    expect(screen.getByText('The two passwords do not match')).toBeInTheDocument()
    expect(screen.getByLabelText(/Repeat new password/)).toBeInvalid()
    await userEvent.type(screen.getByLabelText(/Current password/), 'x')
    expect(save()).toBeDisabled()

    await userEvent.clear(screen.getByLabelText(/Repeat new password/))
    await userEvent.type(screen.getByLabelText(/Repeat new password/), 'Brand-New-9')
    expect(screen.queryByText('The two passwords do not match')).not.toBeInTheDocument()
    expect(save()).toBeEnabled()
  })

  it('sends both passwords, keeps the new session, and opens an employee on My work', async () => {
    signIn('employee')
    let body: unknown
    const calls = mockRoutes({
      'POST /auth/change-password': (config: InternalAxiosRequestConfig) => {
        body = JSON.parse(config.data)
        return { access_token: 'new', expires_at: FUTURE(), user: apiUser('employee', false) }
      },
    })
    renderPage()
    await fill('OneTime123', 'Brand-New-9', 'Brand-New-9')
    await userEvent.click(save())
    expect(await screen.findByText('my work page')).toBeInTheDocument()
    expect(calls).toEqual(['POST /auth/change-password'])
    expect(body).toEqual({ current_password: 'OneTime123', new_password: 'Brand-New-9' })
    const saved = JSON.parse(localStorage.getItem('pm.auth')!)
    expect(saved.token).toBe('new')
    expect(saved.user.mustChangePassword).toBe(false)
  })

  it.each(['manager', 'admin'])('opens a %s on the dashboard', async (role) => {
    signIn(role)
    mockRoutes({ 'POST /auth/change-password': { access_token: 'new', expires_at: FUTURE(), user: apiUser(role, false) } })
    renderPage()
    await fill('OneTime123', 'Brand-New-9', 'Brand-New-9')
    await userEvent.click(save())
    expect(await screen.findByText('dashboard page')).toBeInTheDocument()
  })

  it('shows the server sentence and stays on the page when the current password is wrong', async () => {
    signIn('employee')
    mockRoutes({ 'POST /auth/change-password': apiError(400, 'invalid_password', 'The current password is not correct') })
    renderPage()
    await fill('wrong', 'Brand-New-9', 'Brand-New-9')
    await userEvent.click(save())
    expect(await screen.findByRole('alert')).toHaveTextContent('The current password is not correct')
    expect(screen.queryByText('my work page')).not.toBeInTheDocument()
    await waitFor(() => expect(save()).toBeEnabled())
  })

  it('lists the rules the new password broke', async () => {
    signIn('employee')
    mockRoutes({
      'POST /auth/change-password': apiError(422, 'validation_error', 'Request validation failed', [{ field: 'new_password', message: 'needs an uppercase letter' }]),
    })
    renderPage()
    await fill('OneTime123', 'weakpass1', 'weakpass1')
    await userEvent.click(save())
    expect(await screen.findByRole('alert')).toHaveTextContent('Request validation failed: needs an uppercase letter')
  })

  it('disables Save and says it is saving while the request runs', async () => {
    signIn('employee')
    let finish!: () => void
    // The route helper answers at once, so hold the answer back with an adapter of our own.
    http.defaults.adapter = (config) => new Promise((resolve) => {
      finish = () => resolve({ data: { access_token: 'new', expires_at: FUTURE(), user: apiUser('employee', false) }, status: 200, statusText: '', headers: {}, config })
    })
    renderPage()
    await fill('OneTime123', 'Brand-New-9', 'Brand-New-9')
    await userEvent.click(save())
    expect(await screen.findByRole('button', { name: 'Saving…' })).toBeDisabled()
    finish()
    expect(await screen.findByText('my work page')).toBeInTheDocument()
  })

  it('lets the person sign out instead', async () => {
    signIn('employee')
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByText('sign in page')).toBeInTheDocument()
    expect(localStorage.getItem('pm.auth')).toBeNull()
  })
})
