import { Box, Paper, Stack, Typography } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import type { Project } from '../api/types'
import { dateRange, money, percent } from '../format'
import { PulseBar } from './PulseBar'
import { RiskChip } from './RiskChip'

/** One project at a glance: health, pulse bar, the reasons behind the health, and the key numbers. */
export function ProjectCard({ project }: { project: Project }) {
  const s = project.summary
  return (
    <Paper
      component={RouterLink}
      to={`/projects/${project.id}`}
      sx={{ display: 'block', p: 2.5, textDecoration: 'none', color: 'inherit', '&:hover': { borderColor: 'primary.main', boxShadow: 1 } }}
    >
      <Stack direction="row" spacing={2} sx={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h6" noWrap>{project.name}</Typography>
          <Typography variant="body2" color="text.secondary">
            {project.manager.name} · {dateRange(project.startDate, project.endDate)}
          </Typography>
        </Box>
        <RiskChip level={s.riskLevel} />
      </Stack>

      <Box sx={{ my: 2 }}>
        <PulseBar schedulePct={s.schedulePct} workPct={s.milestonesPct} risk={s.riskLevel} />
      </Box>

      {s.riskReasons.length > 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          {s.riskReasons.join(' · ')}
        </Typography>
      )}

      <Stack direction="row" spacing={3} useFlexGap sx={{ flexWrap: 'wrap' }}>
        <Fact label="Milestones" value={`${s.milestonesDone} of ${s.milestonesTotal}`} />
        <Fact label="Team" value={String(s.teamSize)} />
        {/* The server sends no money to employees, so the figures are simply left out for them. */}
        {s.totalCost !== null && <Fact label="Budget used" value={percent(s.budgetPct)} />}
        {s.totalCost !== null && <Fact label="Spent" value={money(s.totalCost)} />}
      </Stack>
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
