import { createContext, useContext } from 'react'
import type { Role, TokenResponse, User } from '../api/types'

export interface AuthState {
  user: User | null
  /** Sign in with the username and password; resolves to the signed-in user. */
  login: (username: string, password: string) => Promise<User>
  /** Take over a fresh token (used after a password change, which revokes the old one). */
  accept: (response: TokenResponse) => void
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}

/** Where each role lands after signing in. */
export const homeFor = (role: Role) => (role === 'employee' ? '/my-work' : '/dashboard')
