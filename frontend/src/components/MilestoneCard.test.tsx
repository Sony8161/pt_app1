import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { InternalAxiosRequestConfig } from 'axios'
import { keysToCamel } from '../api/case'
import type { Milestone, Project } from '../api/types'
import { apiError, mockRoutes, restoreApi } from '../test/mockApi'
import { deliverable, milestone as milestoneBody, project as projectBody } from '../test/pmFixtures'
import { MilestoneCard } from './MilestoneCard'

// MUI dialogs are slow to open in jsdom on a busy machine.
vi.setConfig({ testTimeout: 30_000 })

const BASE = '/projects/p1/milestones/m1'
const body = (c: InternalAxiosRequestConfig) => JSON.parse(c.data as string)
const list = (items: unknown[]) => ({ items, total: items.length, done: items.filter((i) => (i as { done: boolean }).done).length, ready_to_complete: false })
const person = (id: string, name: string, jobTitle = '') => ({
  id, username: id, name, email: `${id}@x.test`, job_title: jobTitle, role: 'employee', manager_id: null,
  must_change_password: false, archived_at: null, salary: null,
})
const assignee = (overrides: Record<string, unknown> = {}) => ({
  assignment_id: 'a1', user_id: 'u1', name: 'Ann Designer', job_title: 'Designer', milestone_id: 'm1', milestone_name: 'Design',
  start_date: '2026-09-01', end_date: '2026-09-30', days_worked: 10, hours_worked: 80, labor_cost: 2400, ...overrides,
})
const team = (items: unknown[] = []) => ({ items, total: items.length, hours_worked: 0, labor_cost: 0 })

interface Setup {
  milestone?: Record<string, unknown>
  canManage?: boolean
  deliverables?: unknown[]
  team?: unknown[]
  routes?: Record<string, unknown>
}

function setup({ milestone, canManage = true, deliverables = [deliverable(), deliverable({ id: 'd2', name: 'Mockups', done: true })], team: members = [], routes = {} }: Setup = {}) {
  const calls = mockRoutes({
    [`GET ${BASE}/deliverables`]: list(deliverables),
    [`GET ${BASE}/team`]: team(members),
    ...routes,
  })
  const onChanged = vi.fn()
  const view = render(
    <MilestoneCard
      project={keysToCamel<Project>(projectBody())}
      milestone={keysToCamel<Milestone>(milestoneBody(milestone))}
      canManage={canManage}
      onChanged={onChanged}
    />,
  )
  return { calls, onChanged, ...view }
}

afterEach(restoreApi)

describe('MilestoneCard: what it shows', () => {
  it('shows the milestone, its facts, deliverables with their ticks, and the team', async () => {
    setup({ team: [assignee(), assignee({ assignment_id: 'a2', name: 'Bo Builder', job_title: '' })] })
    expect(screen.getByRole('heading', { name: 'Design' })).toBeInTheDocument()
    expect(screen.getByText('Sep 1, 2026 to Oct 31, 2026')).toBeInTheDocument()
    expect(screen.getByText('Wireframes and mockups')).toBeInTheDocument()
    expect(screen.getByText('In progress')).toBeInTheDocument()
    expect(screen.getByText('Planned').nextSibling).toHaveTextContent('100 h')
    expect(screen.getByText('Worked').nextSibling).toHaveTextContent('40 h')
    expect(screen.getByText('Budget').nextSibling).toHaveTextContent('$8,000')
    expect(screen.getByText('Labor so far').nextSibling).toHaveTextContent('$3,200')
    expect(screen.getByText('Deliverables (1 of 2 done)')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Deliverables done' })).toHaveAttribute('aria-valuenow', '50')

    expect(await screen.findByRole('checkbox', { name: 'Wireframes' })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Mockups' })).toBeChecked()
    expect(await screen.findByText('Ann Designer · Designer')).toBeInTheDocument()
    expect(screen.getByText('Bo Builder · Employee')).toBeInTheDocument()
  })

  it('says nobody is assigned when the team is empty', async () => {
    setup()
    expect(await screen.findByText('Nobody assigned yet.')).toBeInTheDocument()
  })

  it('tells a manager to add deliverables, and tells an employee none are listed yet', async () => {
    const { unmount } = setup({ deliverables: [], milestone: { deliverables_total: 0, deliverables_done: 0 } })
    expect(await screen.findByText(/A milestone needs at least one before it can be completed/)).toBeInTheDocument()
    unmount()
    setup({ canManage: false, deliverables: [], milestone: { deliverables_total: 0, deliverables_done: 0 } })
    expect(await screen.findByText('No deliverables have been listed yet.')).toBeInTheDocument()
  })

  it('flags a past-due milestone and shows the status of a milestone that has not started', async () => {
    setup({ milestone: { is_overdue: true, status: 'pending' } })
    expect(screen.getByText('Past due')).toBeInTheDocument()
    expect(screen.getByText('Not started')).toBeInTheDocument()
    await screen.findByText('Nobody assigned yet.')
  })

  it('leaves out the money figures when the server did not send them', async () => {
    setup({ milestone: { budget_amount: null, labor_cost: null, budget_pct: null } })
    await screen.findByText('Nobody assigned yet.')
    expect(screen.queryByText('Budget')).not.toBeInTheDocument()
    expect(screen.queryByText('Labor so far')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('$')
  })

  it('shows the review note of a completed milestone and the label "Completed, archived"', async () => {
    setup({ milestone: { status: 'completed', archived_at: '2026-10-10T00:00:00Z', review_note: 'Signed off by the client' } })
    expect(screen.getByText('Completed, archived')).toBeInTheDocument()
    expect(screen.getByText('Review note: Signed off by the client')).toBeInTheDocument()
    await screen.findByText('Nobody assigned yet.')
  })

  it('labels a cancelled milestone as "Cancelled, archived"', async () => {
    setup({ milestone: { status: 'in_progress', archived_at: '2026-10-10T00:00:00Z' } })
    expect(screen.getByText('Cancelled, archived')).toBeInTheDocument()
    await screen.findByText('Nobody assigned yet.')
  })
})

describe('MilestoneCard: read-only', () => {
  it('lets an employee see the checklist but not change anything', async () => {
    setup({ canManage: false })
    expect(await screen.findByRole('checkbox', { name: 'Wireframes' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Mockups' })).toBeDisabled()
    expect(screen.queryByLabelText('New deliverable')).not.toBeInTheDocument()
    for (const name of ['Assign a person', 'Complete milestone', 'Cancel milestone', 'Mark as started', 'Add']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
  })

  it.each([
    ['completed', { status: 'completed', archived_at: '2026-10-10T00:00:00Z' }],
    ['completed but not yet archived', { status: 'completed' }],
    ['archived', { archived_at: '2026-10-10T00:00:00Z' }],
  ])('locks a manager out of a milestone that is %s', async (_label, milestone) => {
    setup({ milestone })
    expect(await screen.findByRole('checkbox', { name: 'Wireframes' })).toBeDisabled()
    expect(screen.queryByLabelText('New deliverable')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete milestone' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Assign a person' })).not.toBeInTheDocument()
  })
})

describe('MilestoneCard: deliverables', () => {
  it('ticks a deliverable with a PATCH, then reloads the list and tells the page', async () => {
    let items = [deliverable(), deliverable({ id: 'd2', name: 'Mockups', done: true })]
    const patches: unknown[] = []
    const { calls, onChanged } = setup({
      routes: {
        [`GET ${BASE}/deliverables`]: () => list(items),
        [`PATCH ${BASE}/deliverables/:id`]: (c: InternalAxiosRequestConfig) => {
          patches.push([c.url, body(c)])
          items = items.map((d) => (d.id === 'd1' ? { ...d, done: true } : d))
          return items[0]
        },
      },
    })
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Wireframes' }))
    await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Wireframes' })).toBeChecked())
    expect(patches).toEqual([[`${BASE}/deliverables/d1`, { done: true }]])
    expect(onChanged).toHaveBeenCalledTimes(1)
    expect(calls.filter((c) => c === `GET ${BASE}/deliverables`)).toHaveLength(2)
    expect(calls.filter((c) => c === `GET ${BASE}/team`)).toHaveLength(2)
  })

  it('unticks a deliverable by sending done: false', async () => {
    const patches: unknown[] = []
    setup({ routes: { [`PATCH ${BASE}/deliverables/:id`]: (c: InternalAxiosRequestConfig) => { patches.push([c.url, body(c)]); return {} } } })
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Mockups' }))
    await waitFor(() => expect(patches).toEqual([[`${BASE}/deliverables/d2`, { done: false }]]))
  })

  it('shows the server sentence when a tick is refused, and lets the person dismiss it', async () => {
    const { onChanged } = setup({
      routes: { [`PATCH ${BASE}/deliverables/:id`]: apiError(409, 'conflict', 'This deliverable is archived and can no longer be changed') },
    })
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Wireframes' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('This deliverable is archived and can no longer be changed')
    expect(onChanged).not.toHaveBeenCalled()
    await userEvent.click(within(alert).getByRole('button', { name: /close/i }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('adds a deliverable, clears the box and shows the new item', async () => {
    let items = [deliverable()]
    const posts: unknown[] = []
    const { onChanged } = setup({
      deliverables: items,
      routes: {
        [`GET ${BASE}/deliverables`]: () => list(items),
        [`POST ${BASE}/deliverables`]: (c: InternalAxiosRequestConfig) => {
          posts.push(body(c))
          items = [...items, deliverable({ id: 'd3', name: 'Style guide' })]
          return items[1]
        },
      },
    })
    const box = await screen.findByLabelText('New deliverable')
    const add = screen.getByRole('button', { name: 'Add' })
    expect(add).toBeDisabled()
    await userEvent.type(box, '  Style guide  ')
    expect(add).toBeEnabled()
    await userEvent.click(add)

    expect(await screen.findByRole('checkbox', { name: 'Style guide' })).toBeInTheDocument()
    expect(posts).toEqual([{ name: 'Style guide' }])
    expect(box).toHaveValue('')
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  it('ignores a blank name pressed with Enter', async () => {
    const { calls } = setup()
    const box = await screen.findByLabelText('New deliverable')
    await userEvent.type(box, '   {Enter}')
    expect(calls.some((c) => c.startsWith('POST'))).toBe(false)
  })

  it('keeps the typed name and shows the reason when adding fails (duplicate name)', async () => {
    setup({ routes: { [`POST ${BASE}/deliverables`]: apiError(409, 'conflict', 'This milestone already has a deliverable with that name') } })
    const box = await screen.findByLabelText('New deliverable')
    await userEvent.type(box, 'Wireframes{Enter}')
    expect(await screen.findByText('This milestone already has a deliverable with that name')).toBeInTheDocument()
    expect(box).toHaveValue('Wireframes')
  })
})

describe('MilestoneCard: start, assign, complete, cancel', () => {
  it('marks a pending milestone as started, and offers that only while it is pending', async () => {
    const patches: unknown[] = []
    const { onChanged } = setup({
      milestone: { status: 'pending' },
      routes: { [`PATCH ${BASE}`]: (c: InternalAxiosRequestConfig) => { patches.push(body(c)); return {} } },
    })
    await userEvent.click(screen.getByRole('button', { name: 'Mark as started' }))
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    expect(patches).toEqual([{ status: 'in_progress' }])
  })

  it('does not offer "Mark as started" once the milestone is in progress', async () => {
    setup()
    await screen.findByText('Nobody assigned yet.')
    expect(screen.queryByRole('button', { name: 'Mark as started' })).not.toBeInTheDocument()
  })

  describe('assign a person', () => {
    const employees = { items: [person('u1', 'Ann Designer', 'Designer'), person('u2', 'Bo Builder')], total: 2 }

    async function openAssign() {
      await userEvent.click(await screen.findByRole('button', { name: 'Assign a person' }))
      return screen.findByRole('dialog', { name: 'Assign a person to "Design"' })
    }

    it('lists employees, needs one chosen, posts the assignment and refreshes the team', async () => {
      let members: unknown[] = []
      const sent: unknown[] = []
      const params: unknown[] = []
      const { onChanged } = setup({
        routes: {
          [`GET ${BASE}/team`]: () => team(members),
          'GET /users': (c: InternalAxiosRequestConfig) => { params.push({ ...c.params }); return employees },
          [`POST ${BASE}/team`]: (c: InternalAxiosRequestConfig) => { sent.push(body(c)); members = [assignee()]; return assignee() },
        },
      })
      const dialog = await openAssign()
      const submit = within(dialog).getByRole('button', { name: 'Assign' })
      expect(submit).toBeDisabled()
      expect(dialog).toHaveTextContent('Default: 2026-09-01 or today')
      expect(dialog).toHaveTextContent('Default: 2026-10-31')

      await userEvent.click(within(dialog).getByRole('combobox', { name: /Employee/ }))
      expect(within(await screen.findByRole('listbox')).getAllByRole('option').map((o) => o.textContent)).toEqual([
        'Ann Designer · Designer', 'Bo Builder',
      ])
      await userEvent.click(screen.getByRole('option', { name: /Ann Designer/ }))
      expect(submit).toBeEnabled()
      await userEvent.click(submit)

      expect(await screen.findByText('Ann Designer · Designer')).toBeInTheDocument()
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(params).toEqual([{ role: 'employee' }])
      expect(sent).toEqual([{ user_id: 'u1' }])
      expect(onChanged).toHaveBeenCalledTimes(1)
    })

    it('sends the dates when the manager picks them', async () => {
      const sent: unknown[] = []
      setup({
        routes: {
          'GET /users': employees,
          [`POST ${BASE}/team`]: (c: InternalAxiosRequestConfig) => { sent.push(body(c)); return assignee() },
        },
      })
      const dialog = await openAssign()
      await userEvent.click(within(dialog).getByRole('combobox', { name: /Employee/ }))
      await userEvent.click(await screen.findByRole('option', { name: 'Bo Builder' }))
      await userEvent.type(within(dialog).getByLabelText('From (optional)'), '2026-10-05')
      await userEvent.type(within(dialog).getByLabelText('Until (optional)'), '2026-10-09')
      await userEvent.click(within(dialog).getByRole('button', { name: 'Assign' }))
      await waitFor(() => expect(sent).toEqual([{ user_id: 'u2', start_date: '2026-10-05', end_date: '2026-10-09' }]))
    })

    it('shows the 409 overlap message in the dialog and keeps it open for another try', async () => {
      const message = "Bo Builder is already on milestone 'Build' of 'Mobile app' from 2026-10-01 to 2026-10-31. A person works one milestone per day, so choose dates outside that range."
      let attempt = 0
      const { onChanged } = setup({
        routes: {
          'GET /users': employees,
          [`POST ${BASE}/team`]: () => (++attempt === 1 ? apiError(409, 'assignment_overlap', message, [{ field: 'start_date', message: "Overlaps 'Build'" }]) : assignee()),
        },
      })
      const dialog = await openAssign()
      await userEvent.click(within(dialog).getByRole('combobox', { name: /Employee/ }))
      await userEvent.click(await screen.findByRole('option', { name: 'Bo Builder' }))
      await userEvent.click(within(dialog).getByRole('button', { name: 'Assign' }))

      expect(await within(dialog).findByText(message)).toBeInTheDocument()
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(onChanged).not.toHaveBeenCalled()

      // the chosen person is still selected, so a second try goes through
      await userEvent.click(within(dialog).getByRole('button', { name: 'Assign' }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(onChanged).toHaveBeenCalledTimes(1)
    })

    it('says why the employee list is empty when it cannot be loaded', async () => {
      setup({ routes: { 'GET /users': apiError(500, 'server_error', 'Cannot list people right now') } })
      const dialog = await openAssign()
      expect(await within(dialog).findByText('Cannot list people right now')).toBeInTheDocument()
    })
  })

  describe('complete the milestone', () => {
    async function openComplete() {
      await userEvent.click(await screen.findByRole('button', { name: 'Complete milestone' }))
      return screen.findByRole('dialog', { name: 'Complete "Design"' })
    }

    it('lists the open deliverables when the server refuses, then completes after they are done', async () => {
      let items = [deliverable(), deliverable({ id: 'd2', name: 'Mockups' })]
      const sent: unknown[] = []
      const { onChanged } = setup({
        routes: {
          [`GET ${BASE}/deliverables`]: () => list(items),
          [`POST ${BASE}/complete`]: (c: InternalAxiosRequestConfig) => {
            sent.push(body(c))
            const open = items.filter((d) => !d.done).map((d) => d.name)
            return open.length
              ? apiError(409, 'deliverables_incomplete', `${open.length} deliverable(s) are not done yet: ${open.join(', ')}`, open.map((name) => ({ field: 'deliverables', message: name })))
              : milestoneBody({ status: 'completed' })
          },
          [`PATCH ${BASE}/deliverables/:id`]: (c: InternalAxiosRequestConfig) => {
            items = items.map((d) => (c.url?.endsWith(d.id) ? { ...d, done: true } : d))
            return {}
          },
        },
      })
      const dialog = await openComplete()
      expect(dialog).toHaveTextContent('Every deliverable must be ticked')
      await userEvent.type(within(dialog).getByLabelText('Review note'), 'Reviewed with the client')
      await userEvent.click(within(dialog).getByRole('button', { name: 'Sign off and complete' }))

      expect(await within(dialog).findByText('2 deliverable(s) are not done yet: Wireframes, Mockups')).toBeInTheDocument()
      expect(sent).toEqual([{ review_note: 'Reviewed with the client' }])
      expect(onChanged).not.toHaveBeenCalled()

      // the manager closes the dialog, ticks both items, and signs off again
      await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      await userEvent.click(screen.getByRole('checkbox', { name: 'Wireframes' }))
      await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Wireframes' })).toBeChecked())
      await userEvent.click(screen.getByRole('checkbox', { name: 'Mockups' }))
      await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Mockups' })).toBeChecked())
      onChanged.mockClear()

      const again = await openComplete()
      await userEvent.click(within(again).getByRole('button', { name: 'Sign off and complete' }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(sent).toHaveLength(2)
      expect(onChanged).toHaveBeenCalledTimes(1)
    })

    it('sends an empty review note when none is typed', async () => {
      const sent: unknown[] = []
      setup({ routes: { [`POST ${BASE}/complete`]: (c: InternalAxiosRequestConfig) => { sent.push(body(c)); return {} } } })
      const dialog = await openComplete()
      await userEvent.click(within(dialog).getByRole('button', { name: 'Sign off and complete' }))
      await waitFor(() => expect(sent).toEqual([{ review_note: '' }]))
    })

    it('shows the "no deliverables" refusal', async () => {
      setup({ routes: { [`POST ${BASE}/complete`]: apiError(409, 'no_deliverables', 'Add the deliverables to review before completing this milestone') } })
      const dialog = await openComplete()
      await userEvent.click(within(dialog).getByRole('button', { name: 'Sign off and complete' }))
      expect(await within(dialog).findByText('Add the deliverables to review before completing this milestone')).toBeInTheDocument()
    })
  })

  describe('cancel the milestone', () => {
    async function openCancel() {
      await userEvent.click(await screen.findByRole('button', { name: 'Cancel milestone' }))
      return screen.findByRole('dialog', { name: 'Cancel "Design"?' })
    }

    it('archives the milestone after the manager confirms', async () => {
      const { calls, onChanged } = setup({ routes: { [`POST ${BASE}/archive`]: {} } })
      const dialog = await openCancel()
      expect(dialog).toHaveTextContent('Nothing is deleted')
      await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel milestone' }))
      await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
      expect(calls).toContain(`POST ${BASE}/archive`)
    })

    it('does nothing when the manager backs out', async () => {
      const { calls, onChanged } = setup()
      const dialog = await openCancel()
      await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(calls.some((c) => c.startsWith('POST'))).toBe(false)
      expect(onChanged).not.toHaveBeenCalled()
    })

    it('shows the server reason when archiving fails', async () => {
      setup({ routes: { [`POST ${BASE}/archive`]: apiError(403, 'forbidden', 'Only the project manager can cancel a milestone') } })
      const dialog = await openCancel()
      await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel milestone' }))
      expect(await within(dialog).findByText('Only the project manager can cancel a milestone')).toBeInTheDocument()
    })
  })
})
