import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiError } from '../api/client'
import { FormDialog } from './FormDialog'

function setup(onSubmit: () => Promise<unknown>, extra: Partial<Parameters<typeof FormDialog>[0]> = {}) {
  const onClose = vi.fn()
  render(
    <FormDialog open title="Archive Bo?" submitLabel="Archive" onClose={onClose} onSubmit={onSubmit} {...extra}>
      <p>Are you sure?</p>
    </FormDialog>,
  )
  return { onClose }
}

describe('FormDialog', () => {
  it('shows the title, the content and both buttons', async () => {
    setup(() => Promise.resolve())
    const dialog = await screen.findByRole('dialog', { name: 'Archive Bo?' })
    expect(dialog).toHaveTextContent('Are you sure?')
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Archive' })).toBeEnabled()
  })

  it('renders nothing when closed', () => {
    render(<FormDialog open={false} title="Hidden" submitLabel="Go" onClose={() => {}} onSubmit={() => Promise.resolve()} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('submits and closes on success', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const { onClose } = setup(onSubmit)
    await userEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('disables both buttons while the request is running and says it is working', async () => {
    let finish!: () => void
    const { onClose } = setup(() => new Promise<void>((resolve) => { finish = resolve }))
    await userEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    const working = await screen.findByRole('button', { name: 'Working…' })
    expect(working).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    // Clicking outside must not abandon a request that is in flight.
    await userEvent.click(document.querySelector('.MuiBackdrop-root') as HTMLElement)
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    finish()
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('shows the server sentence in the dialog and stays open when the request fails', async () => {
    const { onClose } = setup(() => Promise.reject(new ApiError(409, 'has_work', 'This person still has open milestones')))
    await userEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This person still has open milestones')
    expect(onClose).not.toHaveBeenCalled()
    // Buttons are usable again so the person can retry or cancel.
    expect(screen.getByRole('button', { name: 'Archive' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()
  })

  it('lists the validation reasons in the error', async () => {
    setup(() => Promise.reject(new ApiError(422, 'validation_error', 'Request validation failed', [{ field: 'email', message: 'is already used' }])))
    await userEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Request validation failed: is already used')
  })

  it('clears an old error when the person tries again', async () => {
    const onSubmit = vi.fn().mockRejectedValueOnce(new ApiError(500, 'server_error', 'Try later')).mockResolvedValueOnce(undefined)
    const { onClose } = setup(onSubmit)
    await userEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Try later')
    await userEvent.click(screen.getByRole('button', { name: 'Archive' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(screen.queryByText('Try later')).not.toBeInTheDocument()
  })

  it('closes and forgets an old error when the person clicks outside', async () => {
    const { onClose } = setup(() => Promise.reject(new ApiError(500, 'server_error', 'Try later')))
    await userEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Try later')
    await userEvent.click(document.querySelector('.MuiBackdrop-root') as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Cancel closes without submitting', async () => {
    const onSubmit = vi.fn()
    const { onClose } = setup(onSubmit)
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('keeps the submit button off while the form is not valid', async () => {
    const onSubmit = vi.fn()
    setup(onSubmit, { submitDisabled: true })
    expect(await screen.findByRole('button', { name: 'Archive' })).toBeDisabled()
  })
})
