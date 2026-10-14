import { act, renderHook, waitFor } from '@testing-library/react'
import { ApiError } from './client'
import { errorText, useApi } from './useApi'

/** A loader we settle by hand, so a test controls exactly when each call finishes. */
function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('useApi', () => {
  it('loads when the screen opens and then hands over the data', async () => {
    const load = vi.fn().mockResolvedValue({ n: 1 })
    const { result } = renderHook(() => useApi(load, []))
    expect(result.current).toMatchObject({ loading: true, data: null, error: null })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual({ n: 1 })
    expect(result.current.error).toBeNull()
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('does nothing at all for a null loader', async () => {
    const { result } = renderHook(() => useApi<number>(null, []))
    expect(result.current).toMatchObject({ loading: false, data: null, error: null })
    act(() => result.current.reload())
    expect(result.current).toMatchObject({ loading: false, data: null, error: null })
  })

  it('loads again when a dependency changes', async () => {
    const load = vi.fn((id: string) => Promise.resolve(`item ${id}`))
    const { result, rerender } = renderHook(({ id }) => useApi(() => load(id), [id]), { initialProps: { id: 'a' } })
    await waitFor(() => expect(result.current.data).toBe('item a'))
    rerender({ id: 'b' })
    await waitFor(() => expect(result.current.data).toBe('item b'))
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('reload fetches again and keeps the old data on screen while it runs', async () => {
    const first = deferred<string>()
    const second = deferred<string>()
    const load = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { result } = renderHook(() => useApi<string>(load, []))
    await act(async () => first.resolve('old'))
    expect(result.current.data).toBe('old')

    act(() => result.current.reload())
    expect(result.current.loading).toBe(true)
    expect(result.current.data).toBe('old')

    await act(async () => second.resolve('new'))
    expect(result.current).toMatchObject({ data: 'new', loading: false })
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('a failed reload keeps the data but shows the error, and the next try clears it', async () => {
    const load = vi.fn()
      .mockResolvedValueOnce('fine')
      .mockRejectedValueOnce(new ApiError(500, 'server_error', 'The server is having a bad day'))
      .mockResolvedValueOnce('fine again')
    const { result } = renderHook(() => useApi<string>(load, []))
    await waitFor(() => expect(result.current.data).toBe('fine'))

    act(() => result.current.reload())
    await waitFor(() => expect(result.current.error).toBe('The server is having a bad day'))
    expect(result.current.data).toBe('fine')
    expect(result.current.loading).toBe(false)

    act(() => result.current.reload())
    expect(result.current.error).toBeNull() // cleared as soon as the retry starts
    await waitFor(() => expect(result.current.data).toBe('fine again'))
    expect(result.current.error).toBeNull()
  })

  it('a first load that fails has no data and an error', async () => {
    const load = vi.fn().mockRejectedValue(new ApiError(404, 'not_found', 'No such project'))
    const { result } = renderHook(() => useApi(load, []))
    await waitFor(() => expect(result.current.error).toBe('No such project'))
    expect(result.current.data).toBeNull()
  })

  it('ignores the answer of a load that was replaced by a newer one', async () => {
    const slow = deferred<string>()
    const fast = deferred<string>()
    const loads = { a: slow.promise, b: fast.promise }
    const { result, rerender } = renderHook(({ id }) => useApi(() => loads[id], [id]), { initialProps: { id: 'a' as 'a' | 'b' } })
    rerender({ id: 'b' })
    await act(async () => fast.resolve('B'))
    await act(async () => slow.resolve('A'))
    expect(result.current.data).toBe('B')
  })

  it('ignores the failure of a load that was replaced by a newer one', async () => {
    const slow = deferred<string>()
    const loads = { a: slow.promise, b: Promise.resolve('B') }
    const { result, rerender } = renderHook(({ id }) => useApi(() => loads[id], [id]), { initialProps: { id: 'a' as 'a' | 'b' } })
    rerender({ id: 'b' })
    await waitFor(() => expect(result.current.data).toBe('B'))
    await act(async () => slow.reject(new ApiError(500, 'server_error', 'Late failure')))
    expect(result.current.error).toBeNull()
    expect(result.current.data).toBe('B')
  })
})

describe('errorText', () => {
  it('uses the server sentence for ordinary API errors', () => {
    expect(errorText(new ApiError(409, 'conflict', 'That name is taken', [{ message: 'ignored' }]))).toBe('That name is taken')
  })

  it('adds the reasons to a validation error so people know what to fix', () => {
    const err = new ApiError(422, 'validation_error', 'Request validation failed', [
      { field: 'email', message: 'is not a valid email' },
      { field: 'name', message: 'is required' },
      { message: '' },
    ])
    expect(errorText(err)).toBe('Request validation failed: is not a valid email; is required')
  })

  it('shows just the message when a validation error has no reasons', () => {
    expect(errorText(new ApiError(422, 'validation_error', 'Request validation failed'))).toBe('Request validation failed')
  })

  it('gives a generic sentence for anything that is not an API error', () => {
    expect(errorText(new Error('boom: stack details'))).toBe('Something went wrong. Please try again.')
    expect(errorText('text')).toBe('Something went wrong. Please try again.')
  })
})
