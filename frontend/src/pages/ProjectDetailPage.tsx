import { useState } from 'react'
import { Alert, Box, Button, Paper, Stack, Tab, Tabs, TextField, Typography } from '@mui/material'
import { Link as RouterLink, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Milestone, MilestoneList, Project } from '../api/types'
import { useApi } from '../api/useApi'
import { useAuth } from '../auth/context'
import { Async } from '../components/Async'
import { DateField, NumberField } from '../components/fields'
import { FormDialog } from '../components/FormDialog'
import { MilestoneCard } from '../components/MilestoneCard'
import { PageHeader } from '../components/PageHeader'
import { PulseBar, type PulseTick } from '../components/PulseBar'
import { RiskChip, StatusChip } from '../components/RiskChip'
import { dateRange, formatDate, hours, money, percent, todayIso } from '../format'
import { CostsTab } from './CostsTab'
import { TeamTab } from './TeamTab'

/** Where a milestone's due date falls on the project's calendar, 0 to 100 (for the ticks on the pulse bar). */
function position(project: Project, iso: string): number {
  const day = (s: string) => new Date(`${s}T00:00:00Z`).getTime()
  const span = day(project.endDate) - day(project.startDate)
  return span > 0 ? (100 * (day(iso) - day(project.startDate))) / span : 0
}

export function ProjectDetailPage() {
  const { projectId = '' } = useParams()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const project = useApi(() => api.get<Project>(`/projects/${projectId}`), [projectId])
  const milestones = useApi(
    () => api.get<MilestoneList>(`/projects/${projectId}/milestones`, { include_archived: isAdmin ? 'true' : undefined }),
    [projectId, isAdmin],
  )
  const [tab, setTab] = useState(0)
  const [dialog, setDialog] = useState<'milestone' | 'complete' | 'archive' | null>(null)

  const reloadAll = () => {
    project.reload()
    milestones.reload()
  }

  return (
    <Async state={project}>
      {(p) => {
        const s = p.summary
        const finished = p.status === 'completed' || p.status === 'archived'
        const canManage = !!user && !finished && (isAdmin || (user.role === 'manager' && p.manager.id === user.id))
        const showMoney = s.totalCost !== null
        const ticks: PulseTick[] = (milestones.data?.items ?? [])
          .filter((m) => m.archivedAt === null)
          .map((m) => ({ id: m.id, name: `${m.name}, due ${formatDate(m.dueDate)}`, at: position(p, m.dueDate), late: m.isOverdue }))

        return (
          <>
            <Button component={RouterLink} to="/projects" size="small" sx={{ mb: 1 }}>← All projects</Button>
            <PageHeader
              title={p.name}
              subtitle={<>{p.manager.name} · {dateRange(p.startDate, p.endDate)}</>}
              actions={
                <>
                  <StatusChip status={p.status} />
                  <RiskChip level={s.riskLevel} />
                  {canManage && p.status === 'active' && <Button variant="outlined" onClick={() => setDialog('complete')}>Mark project complete</Button>}
                  {isAdmin && p.status !== 'archived' && <Button color="error" onClick={() => setDialog('archive')}>Archive</Button>}
                </>
              }
            />
            {p.description && <Typography sx={{ mb: 2 }}>{p.description}</Typography>}

            {s.riskReasons.length > 0 && (
              <Alert severity={s.riskLevel === 'overdue' ? 'error' : 'warning'} sx={{ mb: 3 }}>
                <Typography variant="subtitle2">Why this project is {s.riskLevel === 'overdue' ? 'overdue' : 'at risk'}</Typography>
                <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                  {s.riskReasons.map((r) => <li key={r}>{r}</li>)}
                </Box>
              </Alert>
            )}

            <Paper sx={{ p: 2.5, mb: 3 }}>
              <PulseBar schedulePct={s.schedulePct} workPct={s.milestonesPct} risk={s.riskLevel} ticks={ticks} showLabels />
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                The bar fills as milestones are completed; the dark marker is today. Boxes on the bar are open milestones at their due dates.
              </Typography>
            </Paper>

            <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, mb: 3 }}>
              <Tile label="Time" value={s.daysRemaining >= 0 ? `${s.daysRemaining} days left` : `${-s.daysRemaining} days late`} hint={`${percent(s.schedulePct)} of the calendar used`} />
              <Tile label="Milestones" value={`${s.milestonesDone} of ${s.milestonesTotal}`} hint={s.milestonesOverdue ? `${s.milestonesOverdue} past due` : 'none past due'} />
              <Tile label="Hours" value={`${hours(s.hoursWorked)} of ${hours(p.allocatedHours)}`} hint={`${s.teamSize} people on milestones`} />
              {showMoney && <Tile label="Budget" value={`${money(s.totalCost)} of ${money(p.budgetAmount)}`} hint={`Forecast ${money(s.forecastCost)}`} />}
            </Box>

            <Tabs value={tab} onChange={(_, v: number) => setTab(v)} sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }} variant="scrollable">
              <Tab label="Milestones" />
              <Tab label="Team" />
              {showMoney && <Tab label="Costs" />}
            </Tabs>

            {tab === 0 && (
              <Stack spacing={2}>
                {canManage && <Box><Button variant="contained" onClick={() => setDialog('milestone')}>Add milestone</Button></Box>}
                <Async state={milestones}>
                  {(list) => (
                    <>
                      {list.items.length === 0 && <Typography color="text.secondary">No milestones yet. A project is built from milestones, so add the first one.</Typography>}
                      {list.items.map((m: Milestone) => <MilestoneCard key={m.id} project={p} milestone={m} canManage={canManage} onChanged={reloadAll} />)}
                    </>
                  )}
                </Async>
              </Stack>
            )}
            {tab === 1 && <TeamTab projectId={p.id} />}
            {tab === 2 && showMoney && <CostsTab project={p} canManage={canManage} onChanged={reloadAll} />}

            <NewMilestoneDialog open={dialog === 'milestone'} project={p} onClose={() => setDialog(null)} onDone={reloadAll} />
            <FormDialog
              open={dialog === 'complete'} title="Mark this project complete?" submitLabel="Mark complete"
              onClose={() => setDialog(null)} onSubmit={async () => { await api.post(`/projects/${p.id}/complete`); reloadAll() }}
            >
              <Typography>Everyone working on it is free from tomorrow, and the project can no longer be edited.</Typography>
            </FormDialog>
            <FormDialog
              open={dialog === 'archive'} title="Archive this project?" submitLabel="Archive" danger
              onClose={() => setDialog(null)} onSubmit={async () => { await api.post(`/projects/${p.id}/archive`); reloadAll() }}
            >
              <Typography>
                It disappears for managers and employees, but nothing is deleted. You can restore it from the Archive page.
              </Typography>
            </FormDialog>
          </>
        )
      }}
    </Async>
  )
}

function Tile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="h6" component="p">{value}</Typography>
      <Typography variant="caption" color="text.secondary">{hint}</Typography>
    </Paper>
  )
}

function NewMilestoneDialog({ open, project, onClose, onDone }: { open: boolean; project: Project; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [start, setStart] = useState(project.startDate > todayIso() ? project.startDate : todayIso())
  const [due, setDue] = useState(project.endDate)
  const [plannedHours, setPlannedHours] = useState('')
  const [budget, setBudget] = useState('')

  return (
    <FormDialog
      open={open} title="Add a milestone" submitLabel="Add milestone" submitDisabled={!name.trim()}
      onClose={onClose}
      onSubmit={async () => {
        await api.post(`/projects/${project.id}/milestones`, {
          name, description, startDate: start, dueDate: due,
          allocatedHours: Number(plannedHours || 0), budgetAmount: Number(budget || 0),
        })
        setName('')
        setDescription('')
        onDone()
      }}
    >
      <Typography variant="body2" color="text.secondary">
        Dates, hours and budget must fit inside the project ({dateRange(project.startDate, project.endDate)}).
      </Typography>
      <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
      <TextField label="What is this milestone for?" value={description} onChange={(e) => setDescription(e.target.value)} multiline minRows={2} />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <DateField label="Starts" fullWidth value={start} onChange={(e) => setStart(e.target.value)} />
        <DateField label="Due" fullWidth value={due} onChange={(e) => setDue(e.target.value)} />
      </Stack>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <NumberField label="Planned hours" fullWidth value={plannedHours} onChange={(e) => setPlannedHours(e.target.value)} />
        <NumberField label="Budget ($)" fullWidth value={budget} onChange={(e) => setBudget(e.target.value)} />
      </Stack>
    </FormDialog>
  )
}
