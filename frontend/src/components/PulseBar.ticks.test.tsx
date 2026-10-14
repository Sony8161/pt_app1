import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PulseBar } from './PulseBar'

const ticks = [
  { id: 'm1', name: 'Design signed off', at: 25, late: false },
  { id: 'm2', name: 'Beta release', at: 140, late: true },
]

describe('PulseBar milestones and labels', () => {
  it('shows the percentages as text when labels are asked for', () => {
    render(<PulseBar schedulePct={66.6} workPct={20.4} risk="at_risk" showLabels />)
    expect(screen.getByText('Work done 20%')).toBeInTheDocument()
    expect(screen.getByText('Calendar elapsed 67%')).toBeInTheDocument()
  })

  it('has no text labels by default', () => {
    render(<PulseBar schedulePct={10} workPct={10} risk="on_track" />)
    expect(screen.queryByText(/Work done 10%/)).not.toBeInTheDocument()
  })

  it('names a milestone marker when the pointer rests on it', async () => {
    const { container } = render(<PulseBar schedulePct={50} workPct={50} risk="on_track" ticks={ticks} />)
    // Two markers plus the today marker, all absolutely positioned inside the track.
    const track = container.querySelector('[role="img"] > div') as HTMLElement
    const markers = Array.from(track.children).filter((el) => el.getAttribute('title'))
    expect(markers.map((m) => m.getAttribute('title'))).toEqual(['Design signed off', 'Beta release'])
    // The name is a description, not an aria-label: a label on a div with no role is an accessibility error (axe).
    expect(markers.every((m) => !m.hasAttribute('aria-label'))).toBe(true)
    await userEvent.hover(markers[0])
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Design signed off')
  })

  it('keeps a milestone that falls after the end of the project inside the bar', () => {
    const { container } = render(<PulseBar schedulePct={50} workPct={50} risk="on_track" ticks={ticks} />)
    const late = container.querySelector('[title="Beta release"]') as HTMLElement
    expect(late).not.toBeNull()
    expect(late).toHaveStyle({ left: '100%' })
  })
})
