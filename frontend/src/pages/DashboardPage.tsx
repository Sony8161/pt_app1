import { useState } from 'react'
import {
  Alert, Box, Button, Chip, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography,
} from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { api } from '../api/client'
import type { DemoSeedResult, Overview } from '../api/types'
import { errorText, useApi } from '../api/useApi'
import { useAuth } from '../auth/context'
import { Async } from '../components/Async'
import { CredentialsDialog } from '../components/CredentialsDialog'
import { PageHeader } from '../components/PageHeader'
import { ProjectCard } from '../components/ProjectCard'
import { formatDate, money } from '../format'

export function DashboardPage() {
  const { user } = useAuth()
  const state = useApi(() => api.get<Overview>('/reports/overview'), [])
  const [seeded, setSeeded] = useState<DemoSeedResult | null>(null)
  const [seedError, setSeedError] = useState<string | null>(null)
  const [seeding, setSeeding] = useState(false)

  const loadDemo = async () => {
    setSeeding(true)
    setSeedError(null)
    try {
      const result = await api.post<DemoSeedResult>('/admin/seed-demo')
      setSeeded(result)
      if (!result.created) setSeedError(result.message)
      state.reload()
    } catch (err) {
      setSeedError(errorText(err))
    } finally {
      setSeeding(false)
    }
  }

  return (
    <>
      <Async state={state}>
        {(o) => (
          <>
            <PageHeader title="Dashboard" subtitle={`Where every project stands today, ${formatDate(o.asOf)}`} />

            {o.counts.projects === 0 && (
              <Alert
                severity="info"
                sx={{ mb: 3 }}
                action={user?.role === 'admin' ? <Button color="inherit" size="small" disabled={seeding} onClick={loadDemo}>{seeding ? 'Loading…' : 'Load sample data'}</Button> : undefined}
              >
                {user?.role === 'admin'
                  ? 'There are no projects yet. Load sample managers, employees and projects to see how the dashboard looks.'
                  : 'No projects are assigned to you yet.'}
              </Alert>
            )}
            {seedError && <Alert severity="error" sx={{ mb: 3 }}>{seedError}</Alert>}

            <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, mb: 4 }}>
              <Kpi label="Need attention" value={String(o.counts.atRisk + o.counts.overdue)} hint={`${o.counts.overdue} overdue, ${o.counts.atRisk} at risk`} tone={o.counts.atRisk + o.counts.overdue > 0 ? 'warning.main' : undefined} />
              <Kpi label="Active projects" value={String(o.counts.active)} hint={`${o.counts.planned} planned, ${o.counts.completed} completed`} />
              <Kpi label="Spent so far" value={money(o.totals.spent)} hint={`of ${money(o.totals.budget)} budget`} />
              <Kpi label="People free" value={String(o.availablePeople)} hint="not on a milestone today" />
            </Box>

            <Typography variant="h6" gutterBottom>Projects, most urgent first</Typography>
            <Stack spacing={2} sx={{ mb: 4 }}>
              {o.projects.map((p) => <ProjectCard key={p.id} project={p} />)}
            </Stack>

            <Typography variant="h6" gutterBottom>Who is busy and who is free</Typography>
            <TableContainer component={Paper}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Person</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Working on</TableCell>
                    <TableCell align="right">This week</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {o.allocation.map((p) => (
                    <TableRow key={p.userId}>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{p.name}</Typography>
                        <Typography variant="caption" color="text.secondary">{p.jobTitle}</Typography>
                      </TableCell>
                      <TableCell>
                        <Chip size="small" color={p.state === 'available' ? 'success' : 'default'} variant={p.state === 'available' ? 'filled' : 'outlined'} label={p.state === 'available' ? 'Free' : 'Busy'} />
                      </TableCell>
                      <TableCell>
                        {p.currentWork ? (
                          <Typography variant="body2" component={RouterLink} to={`/projects/${p.currentWork.projectId}`} sx={{ color: 'inherit' }}>
                            {p.currentWork.milestoneName} · {p.currentWork.projectName}
                          </Typography>
                        ) : p.nextWork ? (
                          <Typography variant="body2" color="text.secondary">Next: {p.nextWork.milestoneName} from {formatDate(p.nextWork.startDate)}</Typography>
                        ) : (
                          <Typography variant="body2" color="text.secondary">Nothing planned</Typography>
                        )}
                      </TableCell>
                      <TableCell align="right">{p.hoursThisWeek} of {p.weekCapacity} h</TableCell>
                    </TableRow>
                  ))}
                  {o.allocation.length === 0 && (
                    <TableRow><TableCell colSpan={4}><Typography color="text.secondary">No employees yet.</Typography></TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}
      </Async>

      <CredentialsDialog
        open={seeded?.created === true}
        title="Sample accounts created"
        accounts={(seeded?.accounts ?? []).map((a) => ({ name: a.name, role: a.role, username: a.username, password: a.temporaryPassword }))}
        onClose={() => setSeeded(null)}
      />
    </>
  )
}

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: string }) {
  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="h4" sx={{ color: tone }}>{value}</Typography>
      <Typography variant="caption" color="text.secondary">{hint}</Typography>
    </Paper>
  )
}
