import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Loadable } from '../api/useApi'
import { Async } from './Async'

const state = (over: Partial<Loadable<string[]>>): Loadable<string[]> => ({ data: null, error: null, loading: false, reload: () => {}, ...over })
const list = (items: string[]) => <ul>{items.map((i) => <li key={i}>{i}</li>)}</ul>

describe('Async', () => {
  it('shows a spinner while the first load runs', () => {
    render(<Async state={state({ loading: true })}>{list}</Async>)
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
  })

  it('renders the content once there is data', () => {
    render(<Async state={state({ data: ['Ann', 'Bo'] })}>{list}</Async>)
    expect(screen.getByText('Ann')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('treats an empty list as data, not as "still loading"', () => {
    render(<Async state={state({ data: [] })}>{(items) => <p>{items.length} items</p>}</Async>)
    expect(screen.getByText('0 items')).toBeInTheDocument()
  })

  it('shows the error with a retry button when there is nothing to show yet', async () => {
    const reload = vi.fn()
    render(<Async state={state({ error: 'Cannot reach the server', reload })}>{list}</Async>)
    expect(screen.getByRole('alert')).toHaveTextContent('Cannot reach the server')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('keeps the old content next to the error when a reload fails', async () => {
    const reload = vi.fn()
    render(<Async state={state({ data: ['Ann'], error: 'Refresh failed', reload })}>{list}</Async>)
    expect(screen.getByRole('alert')).toHaveTextContent('Refresh failed')
    expect(screen.getByText('Ann')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
