import { Box, LinearProgress, Paper, Stack, Typography } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { api } from '../api/client'
import type { MyDashboard } from '../api/types'
import { useApi } from '../api/useApi'
import { useAuth } from '../auth/context'
import { Async } from '../components/Async'
import { PageHeader } from '../components/PageHeader'
import { ProjectCard } from '../components/ProjectCard'
import { dateRange, formatDate } from '../format'

export function MyWorkPage() {
  const { user } = useAuth()
  const state = useApi(() => api.get<MyDashboard>('/reports/my-dashboard'), [])

  return (
    <Async state={state}>
      {(d) => (
        <>
          <PageHeader title={`Hello, ${user?.name.split(' ')[0] ?? ''}`} subtitle={`Your work, ${formatDate(d.asOf)}`} />

          <Paper sx={{ p: 3, mb: 3, borderColor: d.currentWork ? 'primary.main' : undefined }}>
            <Typography variant="overline" color="text.secondary">Today</Typography>
            {d.currentWork ? (
              <>
                <Typography variant="h5" component="p">{d.currentWork.milestoneName}</Typography>
                <Typography color="text.secondary">
                  {d.currentWork.projectName} · you are on this until {formatDate(d.currentWork.endDate)}
                </Typography>
              </>
            ) : (
              <Typography variant="h6" component="p">You are not on a milestone today.</Typography>
            )}
            <Box sx={{ mt: 2 }}>
              <Stack direction="row" sx={{ justifyContent: 'space-between' }}>
                <Typography variant="body2" color="text.secondary">Hours this week</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{d.hoursThisWeek} of {d.weekCapacity}</Typography>
              </Stack>
              <LinearProgress variant="determinate" value={Math.min(100, (100 * d.hoursThisWeek) / d.weekCapacity)} sx={{ height: 8, borderRadius: 4, mt: 0.5 }} aria-label="Hours this week" />
            </Box>
          </Paper>

          <Typography variant="h6" gutterBottom>My milestones</Typography>
          <Stack spacing={1.5} sx={{ mb: 4 }}>
            {d.myMilestones.length === 0 && <Typography color="text.secondary">Nothing is assigned to you yet.</Typography>}
            {d.myMilestones.map((m) => (
              <Paper key={m.milestoneId} sx={{ p: 2 }}>
                <Typography sx={{ fontWeight: 600 }}>{m.milestoneName}</Typography>
                <Typography variant="body2" color="text.secondary" component={RouterLink} to={`/projects/${m.projectId}`} sx={{ display: 'block', color: 'primary.main' }}>
                  {m.projectName} · you work on it {dateRange(m.startDate, m.endDate)}
                </Typography>
                <Box sx={{ mt: 1.5 }}>
                  <Typography variant="caption" color="text.secondary">
                    {m.deliverablesDone} of {m.deliverablesTotal} deliverables done
                  </Typography>
                  <LinearProgress
                    variant="determinate" color="success" aria-label="Deliverables done" sx={{ height: 6, borderRadius: 3 }}
                    value={m.deliverablesTotal ? (100 * m.deliverablesDone) / m.deliverablesTotal : 0}
                  />
                </Box>
              </Paper>
            ))}
          </Stack>

          {d.projects.length > 0 && (
            <>
              <Typography variant="h6" gutterBottom>My projects</Typography>
              <Stack spacing={2}>{d.projects.map((p) => <ProjectCard key={p.id} project={p} />)}</Stack>
            </>
          )}
        </>
      )}
    </Async>
  )
}
