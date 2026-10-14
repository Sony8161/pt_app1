import { useState } from 'react'
import {
  Alert, Box, Button, Checkbox, Chip, FormControlLabel, LinearProgress, MenuItem, Paper, Stack, TextField, Typography,
} from '@mui/material'
import { api } from '../api/client'
import type { AssigneeList, DeliverableList, Milestone, Project, UserList } from '../api/types'
import { errorText, useApi } from '../api/useApi'
import { dateRange, hours, money } from '../format'
import { DateField } from './fields'
import { FormDialog } from './FormDialog'

interface Props {
  project: Project
  milestone: Milestone
  /** The signed-in person is this project's manager or an admin, and the project is still open. */
  canManage: boolean
  /** Ask the page to refresh its totals after a change here. */
  onChanged: () => void
}

type Dialog = 'assign' | 'complete' | 'cancel' | null

const STATUS_LABEL = { pending: 'Not started', in_progress: 'In progress', completed: 'Completed' } as const

/** One milestone: its checklist of deliverables, who works on it, and the manager's actions on it. */
export function MilestoneCard({ project, milestone: m, canManage, onChanged }: Props) {
  const base = `/projects/${project.id}/milestones/${m.id}`
  const deliverables = useApi(() => api.get<DeliverableList>(`${base}/deliverables`), [m.id])
  const team = useApi(() => api.get<AssigneeList>(`${base}/team`), [m.id])
  const [dialog, setDialog] = useState<Dialog>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [newItem, setNewItem] = useState('')

  const open = canManage && m.archivedAt === null && m.status !== 'completed'
  const refresh = () => {
    deliverables.reload()
    team.reload()
    onChanged()
  }

  const run = async (action: () => Promise<unknown>) => {
    setMessage(null)
    try {
      await action()
      refresh()
    } catch (err) {
      setMessage(errorText(err))
    }
  }

  const progress = m.deliverablesTotal ? (100 * m.deliverablesDone) / m.deliverablesTotal : 0
  const list = deliverables.data

  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" spacing={2} useFlexGap sx={{ justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h6" component="h2">{m.name}</Typography>
          <Typography variant="body2" color="text.secondary">{dateRange(m.startDate, m.dueDate)}</Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          {m.isOverdue && <Chip size="small" color="error" label="Past due" />}
          <Chip size="small" variant="outlined" label={m.archivedAt ? (m.status === 'completed' ? 'Completed, archived' : 'Cancelled, archived') : STATUS_LABEL[m.status]} />
        </Stack>
      </Stack>

      {m.description && <Typography variant="body2" sx={{ mt: 1 }}>{m.description}</Typography>}

      <Stack direction="row" spacing={3} sx={{ mt: 1.5, flexWrap: 'wrap' }} useFlexGap>
        <Fact label="Planned" value={hours(m.allocatedHours)} />
        <Fact label="Worked" value={hours(m.hoursWorked)} />
        {m.budgetAmount !== null && <Fact label="Budget" value={money(m.budgetAmount)} />}
        {m.laborCost !== null && <Fact label="Labor so far" value={money(m.laborCost)} />}
      </Stack>

      <Typography variant="subtitle2" sx={{ mt: 2.5 }}>
        Deliverables ({m.deliverablesDone} of {m.deliverablesTotal} done)
      </Typography>
      <LinearProgress variant="determinate" value={progress} color="success" aria-label="Deliverables done" sx={{ height: 6, borderRadius: 3, my: 1 }} />
      {list?.items.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          {canManage ? 'No deliverables yet. A milestone needs at least one before it can be completed.' : 'No deliverables have been listed yet.'}
        </Typography>
      )}
      <Box>
        {list?.items.map((d) => (
          <FormControlLabel
            key={d.id}
            sx={{ display: 'flex', ml: 0 }}
            control={
              <Checkbox
                checked={d.done}
                disabled={!open}
                onChange={(e) => run(() => api.patch(`${base}/deliverables/${d.id}`, { done: e.target.checked }))}
              />
            }
            label={d.name}
          />
        ))}
      </Box>
      {open && (
        <Stack
          component="form" direction="row" spacing={1} sx={{ mt: 1 }}
          onSubmit={(e) => {
            e.preventDefault()
            const name = newItem.trim()
            if (!name) return
            run(() => api.post(`${base}/deliverables`, { name }).then(() => setNewItem('')))
          }}
        >
          <TextField size="small" fullWidth placeholder="Add a deliverable, e.g. Design file" value={newItem} onChange={(e) => setNewItem(e.target.value)} slotProps={{ htmlInput: { 'aria-label': 'New deliverable' } }} />
          <Button type="submit" variant="outlined" disabled={!newItem.trim()}>Add</Button>
        </Stack>
      )}

      <Typography variant="subtitle2" sx={{ mt: 2.5, mb: 1 }}>Team</Typography>
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
        {team.data?.items.length === 0 && <Typography variant="body2" color="text.secondary">Nobody assigned yet.</Typography>}
        {team.data?.items.map((a) => (
          <Chip key={a.assignmentId} label={`${a.name} · ${a.jobTitle || 'Employee'}`} variant="outlined" />
        ))}
        {open && <Button size="small" onClick={() => setDialog('assign')}>Assign a person</Button>}
      </Stack>

      {m.reviewNote && <Alert severity="success" sx={{ mt: 2 }}>Review note: {m.reviewNote}</Alert>}
      {message && <Alert severity="error" sx={{ mt: 2 }} onClose={() => setMessage(null)}>{message}</Alert>}

      {open && (
        <Stack direction="row" spacing={1} sx={{ mt: 2.5, flexWrap: 'wrap' }} useFlexGap>
          {m.status === 'pending' && (
            <Button variant="outlined" onClick={() => run(() => api.patch(base, { status: 'in_progress' }))}>Mark as started</Button>
          )}
          <Button variant="contained" onClick={() => setDialog('complete')}>Complete milestone</Button>
          <Button color="error" onClick={() => setDialog('cancel')}>Cancel milestone</Button>
        </Stack>
      )}

      <AssignDialog open={dialog === 'assign'} base={base} milestone={m} onClose={() => setDialog(null)} onDone={refresh} />
      <CompleteDialog open={dialog === 'complete'} base={base} milestone={m} onClose={() => setDialog(null)} onDone={refresh} />
      <FormDialog
        open={dialog === 'cancel'} title={`Cancel "${m.name}"?`} submitLabel="Cancel milestone" danger
        onClose={() => setDialog(null)} onSubmit={async () => { await api.post(`${base}/archive`); refresh() }}
      >
        <Typography>
          The milestone moves to the archive, which only admins can see. Nothing is deleted. Everyone on it is free from tomorrow.
        </Typography>
      </FormDialog>
    </Paper>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{label}</Typography>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>{value}</Typography>
    </Box>
  )
}

interface DialogProps { open: boolean; base: string; milestone: Milestone; onClose: () => void; onDone: () => void }

function AssignDialog({ open, base, milestone, onClose, onDone }: DialogProps) {
  const people = useApi(open ? () => api.get<UserList>('/users', { role: 'employee' }) : null, [open])
  const [userId, setUserId] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')

  return (
    <FormDialog
      open={open} title={`Assign a person to "${milestone.name}"`} submitLabel="Assign" submitDisabled={!userId}
      onClose={onClose}
      onSubmit={async () => {
        await api.post(`${base}/team`, { userId, startDate: start || undefined, endDate: end || undefined })
        setUserId('')
        onDone()
      }}
    >
      <Typography variant="body2" color="text.secondary">
        Every Monday to Friday in the range is an 8-hour shift. A person can work only one milestone per day, so the server refuses dates that overlap their other work.
      </Typography>
      <TextField select label="Employee" value={userId} onChange={(e) => setUserId(e.target.value)} required helperText={people.error ?? ' '}>
        {people.data?.items.map((u) => <MenuItem key={u.id} value={u.id}>{u.name}{u.jobTitle ? ` · ${u.jobTitle}` : ''}</MenuItem>)}
      </TextField>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <DateField label="From (optional)" required={false} fullWidth value={start} onChange={(e) => setStart(e.target.value)} helperText={`Default: ${milestone.startDate} or today`} />
        <DateField label="Until (optional)" required={false} fullWidth value={end} onChange={(e) => setEnd(e.target.value)} helperText={`Default: ${milestone.dueDate}`} />
      </Stack>
    </FormDialog>
  )
}

function CompleteDialog({ open, base, milestone, onClose, onDone }: DialogProps) {
  const [note, setNote] = useState('')
  return (
    <FormDialog
      open={open} title={`Complete "${milestone.name}"`} submitLabel="Sign off and complete"
      onClose={onClose}
      onSubmit={async () => {
        await api.post(`${base}/complete`, { reviewNote: note })
        onDone()
      }}
    >
      <Typography variant="body2" color="text.secondary">
        Complete a milestone after you have reviewed its deliverables. Every deliverable must be ticked. The milestone then moves to the archive (still counted in project progress) and its team is free from tomorrow.
      </Typography>
      <TextField label="Review note" placeholder="What did you review? e.g. Wireframes signed off by the client" multiline minRows={2} value={note} onChange={(e) => setNote(e.target.value)} />
    </FormDialog>
  )
}
