import axios, { type AxiosResponse } from 'axios'
import { keysToCamel, keysToSnake } from './case'

/** Every API failure arrives in one shape: {error: {code, message, details}}. This is that shape as an Error. */
export class ApiError extends Error {
  status: number
  code: string
  details: { field?: string; message: string }[]

  constructor(status: number, code: string, message: string, details: { field?: string; message: string }[] = []) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

/**
 * The one axios instance. Empty VITE_API_URL means "same address as the site" (the dev proxy or CloudFront).
 * The timeout is long on purpose: the first call after a quiet period waits for the Lambda container to start.
 */
export const http = axios.create({
  baseURL: `${import.meta.env.VITE_API_URL ?? ''}/api/pm-api`,
  timeout: 100_000,
})

let token: string | null = null
let onUnauthorized: () => void = () => {}

export function setToken(value: string | null) {
  token = value
}

/** The auth layer registers what to do when the server says the session is over (expired, revoked). */
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

// Outgoing: add the login token and turn camelCase body keys into the API's snake_case.
http.interceptors.request.use((config) => {
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  if (config.data !== undefined) config.data = keysToSnake(config.data)
  return config
})

// Incoming: turn snake_case into camelCase, and every failure into an ApiError carrying the server's own sentence.
http.interceptors.response.use(
  (response: AxiosResponse) => {
    response.data = keysToCamel(response.data)
    return response
  },
  (error: unknown) => Promise.reject(toApiError(error)),
)

function toApiError(error: unknown): ApiError {
  if (!axios.isAxiosError(error)) return new ApiError(0, 'unknown_error', 'Something went wrong. Please try again.')
  if (!error.response) {
    return error.code === 'ECONNABORTED'
      ? new ApiError(0, 'timeout', 'The server took too long to answer. Please try again.')
      : new ApiError(0, 'network_error', 'Cannot reach the server. Check your connection and try again.')
  }
  const data = keysToCamel<{ error?: { code?: string; message?: string; details?: ApiError['details'] } } | string>(error.response.data)
  const body = typeof data === 'object' && data !== null ? data.error : undefined
  const apiError = new ApiError(
    error.response.status,
    body?.code ?? 'unknown_error',
    body?.message ?? 'Something went wrong. Please try again.',
    body?.details ?? [],
  )
  // A 401 on a signed-in call means the session ended; a failed login is just a wrong password.
  if (error.response.status === 401 && token && apiError.code !== 'invalid_credentials') onUnauthorized()
  return apiError
}

type Query = Record<string, string | number | boolean | undefined | null>

/** Query parameters without the empty ones (an empty search box should not send `q=`). */
function cleanQuery(query?: Query) {
  return Object.fromEntries(Object.entries(query ?? {}).filter(([, v]) => v !== undefined && v !== null && v !== ''))
}

export const api = {
  get: async <T>(path: string, query?: Query) => (await http.get<T>(path, { params: cleanQuery(query) })).data,
  post: async <T>(path: string, body?: unknown) => (await http.post<T>(path, body ?? {})).data,
  patch: async <T>(path: string, body: unknown) => (await http.patch<T>(path, body)).data,
}
