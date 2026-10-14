import { useState, type FormEvent } from 'react'
import { Alert, Box, Button, Paper, Stack, TextField, Typography } from '@mui/material'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { errorText } from '../api/useApi'
import { homeFor, useAuth } from '../auth/context'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user && !user.mustChangePassword) return <Navigate to={homeFor(user.role)} replace />

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const signedIn = await login(username, password)
      const from = (location.state as { from?: string } | null)?.from
      navigate(signedIn.mustChangePassword ? '/change-password' : (from ?? homeFor(signedIn.role)), { replace: true })
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', px: 2, bgcolor: 'background.default' }}>
      <Paper sx={{ p: { xs: 3, sm: 4 }, width: '100%', maxWidth: 400 }}>
        <Typography variant="h5" component="h1" gutterBottom>ACME Projects</Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          Sign in to see your projects and your work. Your administrator gave you a username and a one-time password.
        </Typography>
        <form onSubmit={submit}>
          <Stack spacing={2}>
            <TextField label="Username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
            <TextField label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            {error && <Alert severity="error">{error}</Alert>}
            <Button type="submit" variant="contained" size="large" disabled={busy || !username || !password}>
              {busy ? 'Signing in…' : 'Sign in'}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Box>
  )
}
