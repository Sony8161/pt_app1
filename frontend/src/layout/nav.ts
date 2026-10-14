import type { Role } from '../api/types'

export interface NavItem {
  label: string
  to: string
  icon: 'dashboard' | 'projects' | 'people' | 'archive' | 'work'
}

/** What each role can open. The server enforces the same rules; this only decides what to show. */
export function navFor(role: Role): NavItem[] {
  if (role === 'employee') return [{ label: 'My work', to: '/my-work', icon: 'work' }]
  const items: NavItem[] = [
    { label: 'Dashboard', to: '/dashboard', icon: 'dashboard' },
    { label: 'Projects', to: '/projects', icon: 'projects' },
    { label: 'People', to: '/people', icon: 'people' },
  ]
  if (role === 'admin') items.push({ label: 'Archive', to: '/archive', icon: 'archive' })
  return items
}
