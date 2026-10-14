import { useCallback, useEffect, useState } from 'react'
import { ApiError } from './client'

export interface Loadable<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

interface Settled<T> { key: string; data: T | null; error: string | null }

/**
 * Load something from the API when the screen opens, whenever `deps` change, and again on `reload`.
 * Passing `null` instead of a loader does nothing (used for data that is only needed once a dialog opens).
 * The previous data stays on screen while a reload is running, so lists do not flash empty after each change.
 */
export function useApi<T>(load: (() => Promise<T>) | null, deps: unknown[]): Loadable<T> {
  const [version, setVersion] = useState(0)
  const [settled, setSettled] = useState<Settled<T> | null>(null)
  const key = JSON.stringify([...deps, version])

  useEffect(() => {
    if (!load) return
    let cancelled = false
    load()
      .then((data) => {
        if (!cancelled) setSettled({ key, data, error: null })
      })
      .catch((err: unknown) => {
        if (!cancelled) setSettled((prev) => ({ key, data: prev?.data ?? null, error: errorText(err) }))
      })
    return () => {
      cancelled = true
    }
    // `load` is a new function on every render; the key (deps + reload counter) is what decides when to fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const reload = useCallback(() => setVersion((v) => v + 1), [])
  return {
    data: settled?.data ?? null,
    error: settled?.key === key ? settled.error : null,
    loading: load !== null && settled?.key !== key,
    reload,
  }
}

/** The text to show a person for any failure: the server's own sentence when it has one. */
export function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    // "Request validation failed" alone tells nobody what to fix; the reasons are in `details`.
    const reasons = err.code === 'validation_error' ? err.details.map((d) => d.message).filter(Boolean) : []
    return reasons.length ? `${err.message}: ${reasons.join('; ')}` : err.message
  }
  return 'Something went wrong. Please try again.'
}
