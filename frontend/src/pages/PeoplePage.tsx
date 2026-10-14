import { useEffect, useState } from 'react'
import {
  Button, Chip, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from '@mui/material'
import { api } from '../api/client'
import type { PasswordReset, Role, User, UserCreated, UserList } from '../api/types'
import { useApi } from '../api/useApi'
import { useAuth } from '../auth/context'
import { Async } from '../components/Async'
import { CredentialsDialog, type Credential } from '../components/CredentialsDialog'
import { NumberField } from '../components/fields'
import { FormDialog } from '../components/FormDialog'
import { PageHeader } from '../components/PageHeader'
import { money } from '../format'

export function PeoplePage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [text, setText] = useState('')
  const [q, setQ] = useState('')
  const [creating, setCreating] = useState(false)
  const [target, setTarget] = useState<{ person: User; action: 'archive' | 'reset' } | null>(null)
  const [credentials, setCredentials] = useState<Credential[] | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => setQ(text.trim()), 300)
    return () => clearTimeout(timer)
  }, [text])

  const state = useApi(() => api.get<UserList>('/users', { q }), [q])
  const managers = useApi(isAdmin ? () => api.get<UserList>('/users', { role: 'manager' }) : null, [isAdmin])

  return (
    <>
      <PageHeader
        title="People"
        subtitle={isAdmin ? 'Everyone with an account. Accounts are archived, never deleted.' : 'The people you can assign to your milestones'}
        actions={isAdmin ? <Button variant="contained" onClick={() => setCreating(true)}>New person</Button> : undefined}
      />
      <TextField size="small" label="Search by name, email or job title" value={text} onChange={(e) => setText(e.target.value)} fullWidth sx={{ mb: 3 }} />
      <Async state={state}>
        {(list) => (
          <TableContainer component={Paper}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Role</TableCell>
                  <TableCell>Username</TableCell>
                  <TableCell>Reports to</TableCell>
                  {isAdmin && <TableCell align="right">Hourly cost</TableCell>}
                  {isAdmin && <TableCell align="right">Actions</TableCell>}
                </TableRow>
              </TableHead>
              <TableBody>
                {list.items.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{p.name}</Typography>
                      <Typography variant="caption" color="text.secondary">{p.jobTitle || p.email}</Typography>
                    </TableCell>
                    <TableCell><Chip size="small" variant="outlined" label={p.role} sx={{ textTransform: 'capitalize' }} /></TableCell>
                    <TableCell sx={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{p.username}</TableCell>
                    <TableCell>{list.items.find((u) => u.id === p.managerId)?.name ?? managers.data?.items.find((m) => m.id === p.managerId)?.name ?? '—'}</TableCell>
                    {isAdmin && <TableCell align="right">{p.salary === null ? '—' : `${money(p.salary)}/h`}</TableCell>}
                    {isAdmin && (
                      <TableCell align="right">
                        {/* Not on your own row: a reset signs you out and shows the new password once. */}
                        {p.id !== user?.id && <Button size="small" onClick={() => setTarget({ person: p, action: 'reset' })}>New password</Button>}
                        {p.id !== user?.id && <Button size="small" color="error" onClick={() => setTarget({ person: p, action: 'archive' })}>Archive</Button>}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
                {list.items.length === 0 && <TableRow><TableCell colSpan={6}><Typography color="text.secondary">Nobody matches.</Typography></TableCell></TableRow>}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Async>

      {isAdmin && (
        <NewPersonDialog
          open={creating} managers={managers.data?.items ?? []} onClose={() => setCreating(false)}
          onCreated={(c) => { setCredentials([{ name: c.user.name, role: c.user.role, username: c.user.username, password: c.temporaryPassword }]); state.reload() }}
        />
      )}
      <FormDialog
        open={target?.action === 'archive'} title={`Archive ${target?.person.name}?`} submitLabel="Archive" danger
        onClose={() => setTarget(null)} onSubmit={async () => { await api.post(`/users/${target!.person.id}/archive`); state.reload() }}
      >
        <Typography>
          They can no longer sign in, and their future work on milestones ends. Nothing is deleted: you can restore them from the Archive page.
        </Typography>
      </FormDialog>
      <FormDialog
        open={target?.action === 'reset'} title={`New password for ${target?.person.name}`} submitLabel="Create new password"
        onClose={() => setTarget(null)}
        onSubmit={async () => {
          const result = await api.post<PasswordReset>(`/users/${target!.person.id}/reset-password`)
          setCredentials([{ name: target!.person.name, username: target!.person.username, password: result.temporaryPassword }])
        }}
      >
        <Typography>Their current password stops working and every open session is signed out. They must choose a new password at the next sign-in.</Typography>
      </FormDialog>
      <CredentialsDialog open={credentials !== null} title="One-time password" accounts={credentials ?? []} onClose={() => setCredentials(null)} />
    </>
  )
}

function NewPersonDialog({ open, managers, onClose, onCreated }: { open: boolean; managers: User[]; onClose: () => void; onCreated: (c: UserCreated) => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [jobTitle, setJobTitle] = useState('')
  const [role, setRole] = useState<Role>('employee')
  const [managerId, setManagerId] = useState('')
  const [salary, setSalary] = useState('')

  return (
    <FormDialog
      open={open} title="Add a person" submitLabel="Create account"
      submitDisabled={!name.trim() || !email.trim() || (role === 'employee' && !managerId)}
      onClose={onClose}
      onSubmit={async () => {
        const created = await api.post<UserCreated>('/users', {
          name, email, jobTitle, role, managerId: role === 'employee' ? managerId : null, salary: Number(salary || 0),
        })
        setName('')
        setEmail('')
        setJobTitle('')
        onCreated(created)
      }}
    >
      <Typography variant="body2" color="text.secondary">The username and a one-time password are generated for you.</Typography>
      <TextField label="Full name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
      <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      <TextField label="Job title" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <TextField select label="Role" fullWidth value={role} onChange={(e) => setRole(e.target.value as Role)}>
          <MenuItem value="employee">Employee</MenuItem>
          <MenuItem value="manager">Manager</MenuItem>
          <MenuItem value="admin">Admin</MenuItem>
        </TextField>
        <NumberField label="Hourly cost ($)" fullWidth value={salary} onChange={(e) => setSalary(e.target.value)} />
      </Stack>
      {role === 'employee' && (
        <TextField select label="Reports to (their one manager)" value={managerId} onChange={(e) => setManagerId(e.target.value)} required>
          {managers.map((m) => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
        </TextField>
      )}
    </FormDialog>
  )
}
