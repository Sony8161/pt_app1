import { useState, type FormEvent } from 'react'
import { Alert, Box, Button, Paper, Stack, TextField, Typography } from '@mui/material'
import { Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { TokenResponse } from '../api/types'
import { errorText } from '../api/useApi'
import { homeFor, useAuth } from '../auth/context'

export function ChangePasswordPage() {
  const { user, accept, logout } = useAuth()
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!user) return <Navigate to="/login" replace />

  const mismatch = confirm !== '' && confirm !== next

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      // The server revokes the old token and hands back a new one, so we stay signed in.
      const response = await api.post<TokenResponse>('/auth/change-password', { currentPassword: current, newPassword: next })
      accept(response)
      navigate(homeFor(response.user.role), { replace: true })
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', px: 2, bgcolor: 'background.default' }}>
      <Paper sx={{ p: { xs: 3, sm: 4 }, width: '100%', maxWidth: 420 }}>
        <Typography variant="h5" component="h1" gutterBottom>Choose a new password</Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          {user.mustChangePassword ? 'Your one-time password only works once. ' : ''}
          Use at least 8 characters with an uppercase letter, a lowercase letter and a number.
        </Typography>
        <form onSubmit={submit}>
          <Stack spacing={2}>
            <TextField label="Current password" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required autoFocus />
            <TextField label="New password" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required />
            <TextField
              label="Repeat new password" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password" required error={mismatch} helperText={mismatch ? 'The two passwords do not match' : ' '}
            />
            {error && <Alert severity="error">{error}</Alert>}
            <Button type="submit" variant="contained" size="large" disabled={busy || !current || !next || next !== confirm}>
              {busy ? 'Saving…' : 'Save new password'}
            </Button>
            <Button onClick={logout} color="inherit">Sign out</Button>
          </Stack>
        </form>
      </Paper>
    </Box>
  )
}
