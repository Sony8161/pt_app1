import { useEffect, useState } from 'react'
import { Button, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { api } from '../api/client'
import type { ProjectList, UserList } from '../api/types'
import { useApi } from '../api/useApi'
import { useAuth } from '../auth/context'
import { Async } from '../components/Async'
import { DateField, NumberField } from '../components/fields'
import { FormDialog } from '../components/FormDialog'
import { PageHeader } from '../components/PageHeader'
import { ProjectCard } from '../components/ProjectCard'
import { todayIso } from '../format'

export function ProjectsPage() {
  const { user } = useAuth()
  const [text, setText] = useState('')
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [creating, setCreating] = useState(false)

  // Wait for a pause in typing before asking the server, so a search is one request, not one per letter.
  useEffect(() => {
    const timer = setTimeout(() => setQ(text.trim()), 300)
    return () => clearTimeout(timer)
  }, [text])

  const state = useApi(() => api.get<ProjectList>('/projects', { q, status, page_size: 100 }), [q, status])

  return (
    <>
      <PageHeader
        title="Projects"
        subtitle={user?.role === 'employee' ? 'The projects you work on' : user?.role === 'manager' ? 'The projects you run' : 'Every project in the company'}
        actions={user?.role === 'admin' ? <Button variant="contained" onClick={() => setCreating(true)}>New project</Button> : undefined}
      />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
        <TextField size="small" label="Search by project or manager" value={text} onChange={(e) => setText(e.target.value)} sx={{ flex: 1 }} />
        <TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 160 }}>
          <MenuItem value="">All</MenuItem>
          <MenuItem value="planned">Planned</MenuItem>
          <MenuItem value="active">Active</MenuItem>
          <MenuItem value="completed">Completed</MenuItem>
        </TextField>
      </Stack>
      <Async state={state}>
        {(list) => (
          <Stack spacing={2}>
            {list.items.length === 0 && <Typography color="text.secondary">No projects match.</Typography>}
            {list.items.map((p) => <ProjectCard key={p.id} project={p} />)}
          </Stack>
        )}
      </Async>
      {user?.role === 'admin' && <NewProjectDialog open={creating} onClose={() => setCreating(false)} onDone={state.reload} />}
    </>
  )
}

function NewProjectDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const managers = useApi(open ? () => api.get<UserList>('/users', { role: 'manager' }) : null, [open])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [managerId, setManagerId] = useState('')
  const [start, setStart] = useState(todayIso())
  const [end, setEnd] = useState(todayIso(90))
  const [projectHours, setProjectHours] = useState('')
  const [budget, setBudget] = useState('')

  return (
    <FormDialog
      open={open} title="Create a project" submitLabel="Create project" submitDisabled={!name.trim() || !managerId}
      onClose={onClose}
      onSubmit={async () => {
        await api.post('/projects', {
          name, description, managerId, startDate: start, endDate: end,
          allocatedHours: Number(projectHours || 0), budgetAmount: Number(budget || 0),
        })
        setName('')
        setDescription('')
        onDone()
      }}
    >
      <Typography variant="body2" color="text.secondary">Each project has exactly one manager, who then plans its milestones and team.</Typography>
      <TextField label="Project name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
      <TextField label="Description" value={description} onChange={(e) => setDescription(e.target.value)} multiline minRows={2} />
      <TextField select label="Manager" value={managerId} onChange={(e) => setManagerId(e.target.value)} required helperText={managers.error ?? ' '}>
        {managers.data?.items.map((m) => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
      </TextField>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <DateField label="Starts" fullWidth value={start} onChange={(e) => setStart(e.target.value)} />
        <DateField label="Predicted end" fullWidth value={end} onChange={(e) => setEnd(e.target.value)} />
      </Stack>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <NumberField label="Total hours" fullWidth value={projectHours} onChange={(e) => setProjectHours(e.target.value)} />
        <NumberField label="Budget ($)" fullWidth value={budget} onChange={(e) => setBudget(e.target.value)} />
      </Stack>
    </FormDialog>
  )
}
