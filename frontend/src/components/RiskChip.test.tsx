import { render, screen } from '@testing-library/react'
import type { ProjectStatus, RiskLevel } from '../api/types'
import { RiskChip, StatusChip } from './RiskChip'

describe('RiskChip', () => {
  it.each<[RiskLevel, string, string]>([
    ['on_track', 'On track', 'colorSuccess'],
    ['at_risk', 'At risk', 'colorWarning'],
    ['overdue', 'Overdue', 'colorError'],
    ['done', 'Done', 'colorDefault'],
  ])('says %s in words (%s) so colour is never the only signal', (level, text, colourClass) => {
    render(<RiskChip level={level} />)
    const chip = screen.getByText(text).closest('.MuiChip-root')!
    expect(chip.className).toContain(colourClass)
  })

  it('draws a finished project as an outline, the others filled', () => {
    const { rerender } = render(<RiskChip level="done" />)
    expect(screen.getByText('Done').closest('.MuiChip-root')!.className).toContain('outlined')
    rerender(<RiskChip level="overdue" />)
    expect(screen.getByText('Overdue').closest('.MuiChip-root')!.className).toContain('filled')
  })
})

describe('StatusChip', () => {
  it.each<[ProjectStatus, string]>([
    ['planned', 'Planned'], ['active', 'Active'], ['completed', 'Completed'], ['archived', 'Archived'],
  ])('writes %s as %s', (status, text) => {
    render(<StatusChip status={status} />)
    expect(screen.getByText(text)).toBeInTheDocument()
  })
})
