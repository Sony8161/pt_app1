import { mockApi, mockNoAnswer, restoreApi } from '../test/mockApi'
import { ApiError, api, setToken, setUnauthorizedHandler } from './client'

afterEach(() => {
  restoreApi()
  setToken(null)
  setUnauthorizedHandler(() => {})
})

describe('api client (axios)', () => {
  it('sends the token and converts keys both ways', async () => {
    const sent = mockApi(200, { project_id: 'p1' })
    setToken('abc')
    const out = await api.post<{ projectId: string }>('/projects', { managerId: 'm1' })
    expect(out.projectId).toBe('p1')
    expect(sent[0].baseURL).toMatch(/\/api\/pm-api$/) // with or without VITE_API_URL
    expect(sent[0].url).toBe('/projects')
    expect(sent[0].headers.get('Authorization')).toBe('Bearer abc')
    expect(JSON.parse(sent[0].data)).toEqual({ manager_id: 'm1' })
  })

  it('turns the API error shape into an ApiError with the server sentence', async () => {
    mockApi(409, { error: { code: 'assignment_overlap', message: 'Alex is already on another milestone', details: [{ field: 'start_date', message: 'Overlaps' }] } })
    await expect(api.post('/x')).rejects.toMatchObject({
      status: 409, code: 'assignment_overlap', message: 'Alex is already on another milestone', details: [{ field: 'start_date', message: 'Overlaps' }],
    })
  })

  it('drops empty query values and sends the rest', async () => {
    const sent = mockApi(200, { items: [] })
    await api.get('/projects', { q: '', status: 'active', page_size: 10, manager_id: undefined })
    expect(sent[0].params).toEqual({ status: 'active', page_size: 10 })
  })

  it('signs the user out when a signed-in call gets 401, but not on a wrong password', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    setToken('abc')
    mockApi(401, { error: { code: 'token_revoked', message: 'Please sign in again' } })
    await expect(api.get('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(handler).toHaveBeenCalledTimes(1)

    mockApi(401, { error: { code: 'invalid_credentials', message: 'Invalid username or password' } })
    await expect(api.post('/auth/login', {})).rejects.toBeInstanceOf(ApiError)
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('explains a dropped connection and a timeout in plain words', async () => {
    mockNoAnswer('ERR_NETWORK')
    await expect(api.get('/health')).rejects.toMatchObject({ code: 'network_error', message: expect.stringContaining('Cannot reach the server') })
    mockNoAnswer('ECONNABORTED')
    await expect(api.get('/health')).rejects.toMatchObject({ code: 'timeout', message: expect.stringContaining('too long') })
  })

  it('still gives a readable error when the answer is not the API error shape (for example a proxy page)', async () => {
    mockApi(502, '<html>Bad Gateway</html>')
    await expect(api.get('/health')).rejects.toMatchObject({ status: 502, code: 'unknown_error', message: expect.stringContaining('Something went wrong') })
  })
})
