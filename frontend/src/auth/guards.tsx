import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import type { Role } from '../api/types'
import { homeFor, useAuth } from './context'

/** Signed-in users only; a forced password change comes before anything else. */
export function RequireAuth() {
  const { user } = useAuth()
  const location = useLocation()
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (user.mustChangePassword) return <Navigate to="/change-password" replace />
  return <Outlet />
}

/** Sends people who open a page their role does not use back to their own home page. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth()
  if (!user) return null
  if (!roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />
  return <>{children}</>
}
