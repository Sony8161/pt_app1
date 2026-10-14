import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { Project } from '../api/types'
import { ProjectCard } from './ProjectCard'

const project = (summary: Partial<Project['summary']> = {}): Project => ({
  id: 'p1', name: 'Apollo', description: '', manager: { id: 'm1', name: 'Maya Chen' }, status: 'active',
  startDate: '2026-03-02', endDate: '2026-06-26', allocatedHours: 400, budgetAmount: 100000, completedAt: null, archivedAt: null,
  summary: {
    daysTotal: 100, daysElapsed: 40, daysRemaining: 60, schedulePct: 40, hoursWorked: 100, hoursRemaining: 300, hoursPct: 25,
    milestonesTotal: 5, milestonesDone: 2, milestonesOverdue: 0, milestonesPct: 40, teamSize: 4, riskLevel: 'on_track', riskReasons: [],
    laborCost: 30000, forecastCost: 80000, otherCost: 5000, totalCost: 35000, budgetRemaining: 65000, budgetPct: 35, ...summary,
  },
})

const renderCard = (p: Project) => render(<MemoryRouter><ProjectCard project={p} /></MemoryRouter>)

describe('ProjectCard', () => {
  it('shows the project at a glance and links to its page', () => {
    renderCard(project())
    expect(screen.getByRole('link')).toHaveAttribute('href', '/projects/p1')
    expect(screen.getByText('Apollo')).toBeInTheDocument()
    expect(screen.getByText(/Maya Chen · Mar 2, 2026 to Jun 26, 2026/)).toBeInTheDocument()
    expect(screen.getByText('On track')).toBeInTheDocument()
    expect(screen.getByText('2 of 5')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAccessibleName('Work done 40 percent, calendar elapsed 40 percent')
  })

  it('shows budget used and money spent to people who may see money', () => {
    renderCard(project())
    expect(screen.getByText('Budget used')).toBeInTheDocument()
    expect(screen.getByText('35%')).toBeInTheDocument()
    expect(screen.getByText('Spent')).toBeInTheDocument()
    expect(screen.getByText('$35,000')).toBeInTheDocument()
  })

  it('leaves out every money figure when the server sent none (employees)', () => {
    renderCard(project({ totalCost: null, budgetPct: null, laborCost: null }))
    expect(screen.queryByText('Budget used')).not.toBeInTheDocument()
    expect(screen.queryByText('Spent')).not.toBeInTheDocument()
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument()
    expect(screen.getByText('Milestones')).toBeInTheDocument()
  })

  it('lists the reasons behind the health when there are any', () => {
    renderCard(project({ riskLevel: 'at_risk', riskReasons: ['Work is behind the calendar', '1 milestone due this week'] }))
    expect(screen.getByText('At risk')).toBeInTheDocument()
    expect(screen.getByText('Work is behind the calendar · 1 milestone due this week')).toBeInTheDocument()
  })

  it('shows a project with no milestones as 0 of 0', () => {
    renderCard(project({ milestonesTotal: 0, milestonesDone: 0, milestonesPct: null }))
    expect(screen.getByText('0 of 0')).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAccessibleName('Work done 0 percent, calendar elapsed 40 percent')
  })
})
