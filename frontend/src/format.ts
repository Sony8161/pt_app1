import type { RiskLevel } from './api/types'

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

/** Dollars, or an em dash when the server hid the figure (employees never see money). */
export const money = (value: number | null | undefined) => (value === null || value === undefined ? '—' : usd.format(value))

export const percent = (value: number | null | undefined) => (value === null || value === undefined ? '—' : `${Math.round(value)}%`)

export const hours = (value: number) => `${Math.round(value).toLocaleString('en-US')} h`

/** 'YYYY-MM-DD' to 'Mar 9, 2026'. Built from the parts so the browser's time zone cannot shift the day. */
export function formatDate(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export const dateRange = (start: string, end: string) => `${formatDate(start)} to ${formatDate(end)}`

export const RISK_LABEL: Record<RiskLevel, string> = {
  on_track: 'On track',
  at_risk: 'At risk',
  overdue: 'Overdue',
  done: 'Done',
}

export const RISK_COLOR: Record<RiskLevel, 'success' | 'warning' | 'error' | 'default'> = {
  on_track: 'success',
  at_risk: 'warning',
  overdue: 'error',
  done: 'default',
}

/** 'YYYY-MM-DD' for today in the browser's local calendar (used only to pre-fill date pickers). */
export function todayIso(offsetDays = 0): string {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
