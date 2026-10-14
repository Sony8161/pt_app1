import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'
import { http } from '../api/client'

const realAdapter = http.defaults.adapter

/** Answer every API call with this status and body (no network). Returns the requests the app sent, for assertions. */
export function mockApi(status: number, body: unknown): InternalAxiosRequestConfig[] {
  const sent: InternalAxiosRequestConfig[] = []
  const adapter: AxiosAdapter = async (config) => {
    sent.push(config)
    const response = { data: body, status, statusText: '', headers: {}, config }
    if (status >= 400) throw new AxiosError(`status ${status}`, 'ERR_BAD_REQUEST', config, null, response)
    return response
  }
  http.defaults.adapter = adapter
  return sent
}

/** Make every API call fail the way a dropped connection does, or with a timeout. */
export function mockNoAnswer(code: 'ERR_NETWORK' | 'ECONNABORTED' = 'ERR_NETWORK') {
  http.defaults.adapter = async (config) => {
    throw new AxiosError('no answer', code, config)
  }
}

export function restoreApi() {
  http.defaults.adapter = realAdapter
}

/** A reply with a non-200 status, for route handlers: `reply(409, { error: ... })` or `apiError(409, 'code', 'text')`. */
export const reply = (status: number, body: unknown) => ({ __reply: true as const, status, body })
export const apiError = (status: number, code: string, message: string, details: { field?: string; message: string }[] = []) =>
  reply(status, { error: { code, message, details } })

type Handler = unknown | ((config: InternalAxiosRequestConfig) => unknown)

/**
 * Answer API calls by route, for page tests. Keys are `"METHOD /path"`; `:id` matches one path segment.
 * A value is the response body (snake_case, like the real API), a `reply(...)`, or a function returning either.
 * A call with no matching route fails with a 404 that names it, so a missing mock is obvious in the test output.
 * Returns the list of requests the app made, as `"METHOD /path"` strings, for assertions.
 */
export function mockRoutes(routes: Record<string, Handler>): string[] {
  const compiled = Object.entries(routes).map(([key, handler]) => {
    const [method, path] = key.split(' ')
    const pattern = new RegExp(`^${path.replace(/:[a-z_]+/gi, '[^/]+')}$`)
    return { method, pattern, handler }
  })
  const calls: string[] = []
  http.defaults.adapter = async (config) => {
    const method = (config.method ?? 'get').toUpperCase()
    const path = config.url ?? ''
    calls.push(`${method} ${path}`)
    const match = compiled.find((r) => r.method === method && r.pattern.test(path))
    let result: unknown = match
      ? match.handler
      : reply(404, { error: { code: 'no_mock', message: `No mock for ${method} ${path}`, details: [] } })
    if (typeof result === 'function') result = (result as (c: InternalAxiosRequestConfig) => unknown)(config)
    const r = result as { __reply?: true; status: number; body: unknown }
    const status = r && r.__reply ? r.status : 200
    const response = { data: r && r.__reply ? r.body : result, status, statusText: '', headers: {}, config }
    if (status >= 400) throw new AxiosError(`status ${status}`, 'ERR_BAD_REQUEST', config, null, response)
    return response
  }
  return calls
}
