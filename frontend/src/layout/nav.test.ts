import { navFor } from './nav'

describe('navFor', () => {
  it('gives an employee only their own work', () => {
    expect(navFor('employee')).toEqual([{ label: 'My work', to: '/my-work', icon: 'work' }])
  })

  it('gives a manager the dashboard, projects and people, but no archive', () => {
    expect(navFor('manager').map((i) => i.to)).toEqual(['/dashboard', '/projects', '/people'])
  })

  it('gives an admin everything a manager has plus the archive', () => {
    expect(navFor('admin').map((i) => i.label)).toEqual(['Dashboard', 'Projects', 'People', 'Archive'])
  })
})
