import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useAuth } from './context'
import { AuthProvider } from './AuthProvider'
import { mockApi, mockRoutes, restoreApi } from '../test/mockApi'

const FUTURE = () => Math.floor(Date.now() / 1000) + 8 * 3600
const user = { id: '1', username: 'ab12cd', name: 'Alex Kim', email: 'a@x.test', job_title: '', role: 'employee', manager_id: null, must_change_password: false, archived_at: null, salary: null }

function Who() {
  const { user } = useAuth()
  return <p>{user ? `signed in as ${user.name}` : 'signed out'}</p>
}
const app = () => render(<MemoryRouter><AuthProvider><Who /></AuthProvider></MemoryRouter>)

afterEach(() => {
  vi.useRealTimers()
  restoreApi()
  localStorage.clear()
})

describe('AuthProvider', () => {
  it('drops a saved session that has already expired', () => {
    localStorage.setItem('pm.auth', JSON.stringify({ token: 't', expiresAt: Math.floor(Date.now() / 1000) - 60, user: { ...user, mustChangePassword: false } }))
    app()
    expect(screen.getByText('signed out')).toBeInTheDocument()
  })

  it('restores a saved session that is still valid', () => {
    localStorage.setItem('pm.auth', JSON.stringify({ token: 't', expiresAt: FUTURE(), user: { ...user, mustChangePassword: false } }))
    app()
    expect(screen.getByText('signed in as Alex Kim')).toBeInTheDocument()
  })

  it('swaps the token for a fresh one shortly before it expires', async () => {
    vi.useFakeTimers()
    const soon = Math.floor(Date.now() / 1000) + 11 * 60 // expires in 11 minutes: refresh is due in 1 minute
    localStorage.setItem('pm.auth', JSON.stringify({ token: 'old', expiresAt: soon, user: { ...user, mustChangePassword: false } }))
    const calls = mockRoutes({ 'POST /auth/refresh': { access_token: 'new', expires_at: FUTURE(), user: { ...user, name: 'Alex Refreshed' } } })
    app()
    await act(async () => { await vi.advanceTimersByTimeAsync(61_000) })
    expect(calls).toContain('POST /auth/refresh')
    expect(screen.getByText('signed in as Alex Refreshed')).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem('pm.auth')!).token).toBe('new')
  })

  it('signs out when the server refuses the refresh (session revoked)', async () => {
    vi.useFakeTimers()
    const soon = Math.floor(Date.now() / 1000) + 11 * 60
    localStorage.setItem('pm.auth', JSON.stringify({ token: 'old', expiresAt: soon, user: { ...user, mustChangePassword: false } }))
    mockApi(401, { error: { code: 'token_revoked', message: 'Please sign in again' } })
    app()
    await act(async () => { await vi.advanceTimersByTimeAsync(61_000) })
    expect(screen.getByText('signed out')).toBeInTheDocument()
    expect(localStorage.getItem('pm.auth')).toBeNull()
  })
})
