import { Box, Tooltip, Typography } from '@mui/material'
import type { RiskLevel } from '../api/types'

export interface PulseTick {
  id: string
  name: string
  /** Where the milestone falls on the project's calendar, 0 to 100. */
  at: number
  late: boolean
}

interface Props {
  /** Share of the calendar that has passed (0 to 100). Drawn as the "today" marker. */
  schedulePct: number
  /** Share of milestones completed (0 to 100), or null when there are none. Drawn as the fill. */
  workPct: number | null
  risk: RiskLevel
  ticks?: PulseTick[]
  showLabels?: boolean
}

const FILL: Record<RiskLevel, string> = {
  on_track: 'success.main',
  at_risk: 'warning.main',
  overdue: 'error.main',
  done: 'grey.500',
}

const clamp = (n: number) => Math.min(100, Math.max(0, n))

/**
 * The signature element: one bar that answers "is the work keeping pace with the calendar?".
 * The fill is the work done, the dark marker is today. Fill short of the marker means behind schedule.
 */
export function PulseBar({ schedulePct, workPct, risk, ticks = [], showLabels = false }: Props) {
  const work = clamp(workPct ?? 0)
  const today = clamp(schedulePct)
  const label = `Work done ${Math.round(work)} percent, calendar elapsed ${Math.round(today)} percent`

  return (
    <Box role="img" aria-label={label} sx={{ width: '100%' }}>
      <Box sx={{ position: 'relative', height: 12, borderRadius: 6, bgcolor: 'grey.200', overflow: 'visible' }}>
        <Box sx={{ height: '100%', width: `${work}%`, borderRadius: 6, bgcolor: FILL[risk], transition: 'width .3s' }} />
        {ticks.map((tick) => (
          <Tooltip key={tick.id} title={tick.name} arrow describeChild>
            <Box
              sx={{
                position: 'absolute', top: -3, left: `${clamp(tick.at)}%`, width: 8, height: 18, ml: '-4px',
                borderRadius: 1, bgcolor: tick.late ? 'error.main' : 'background.paper',
                border: 2, borderColor: tick.late ? 'error.main' : 'text.secondary',
              }}
            />
          </Tooltip>
        ))}
        <Box sx={{ position: 'absolute', top: -5, left: `${today}%`, width: 3, height: 22, ml: '-1.5px', bgcolor: 'text.primary', borderRadius: 2 }} />
      </Box>
      {showLabels && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
          <Typography variant="caption" color="text.secondary">Work done {Math.round(work)}%</Typography>
          <Typography variant="caption" color="text.secondary">Calendar elapsed {Math.round(today)}%</Typography>
        </Box>
      )}
    </Box>
  )
}
