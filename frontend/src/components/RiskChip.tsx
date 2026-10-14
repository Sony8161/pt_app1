import { Chip } from '@mui/material'
import type { ProjectStatus, RiskLevel } from '../api/types'
import { RISK_COLOR, RISK_LABEL } from '../format'

/** Health of a project. The words carry the meaning too, so colour-blind users lose nothing. */
export function RiskChip({ level }: { level: RiskLevel }) {
  return <Chip size="small" color={RISK_COLOR[level]} variant={level === 'done' ? 'outlined' : 'filled'} label={RISK_LABEL[level]} />
}

const STATUS_LABEL: Record<ProjectStatus, string> = { planned: 'Planned', active: 'Active', completed: 'Completed', archived: 'Archived' }

export function StatusChip({ status }: { status: ProjectStatus }) {
  return <Chip size="small" variant="outlined" label={STATUS_LABEL[status]} />
}
