import { render, screen } from '@testing-library/react'
import { PulseBar } from './PulseBar'

describe('PulseBar', () => {
  it('describes work done against calendar elapsed for screen readers', () => {
    render(<PulseBar schedulePct={67.4} workPct={33.3} risk="on_track" />)
    expect(screen.getByRole('img')).toHaveAccessibleName('Work done 33 percent, calendar elapsed 67 percent')
  })

  it('treats a project with no milestones as 0 percent done and clamps nonsense values', () => {
    render(<PulseBar schedulePct={140} workPct={null} risk="overdue" />)
    expect(screen.getByRole('img')).toHaveAccessibleName('Work done 0 percent, calendar elapsed 100 percent')
  })
})
