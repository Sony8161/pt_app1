import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CredentialsDialog, type Credential } from './CredentialsDialog'

const accounts: Credential[] = [
  { name: 'Ann Lee', role: 'manager', username: 'al12ab', password: 'Pw-One-111' },
  { name: 'Bo Ray', password: 'Pw-Two-222' },
]

describe('CredentialsDialog', () => {
  let writeText: ReturnType<typeof vi.fn>
  beforeEach(() => {
    writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  })

  it('shows each account with its one-time password and the warning', async () => {
    render(<CredentialsDialog open title="One-time password" accounts={accounts} onClose={() => {}} />)
    const dialog = await screen.findByRole('dialog', { name: 'One-time password' })
    expect(dialog).toHaveTextContent('shown only once')
    expect(dialog).toHaveTextContent('Ann Lee · manager')
    expect(dialog).toHaveTextContent('username al12ab')
    expect(dialog).toHaveTextContent('password Pw-One-111')
    expect(dialog).toHaveTextContent('password Pw-Two-222')
  })

  it('does not close on Esc', async () => {
    const onClose = vi.fn()
    render(<CredentialsDialog open title="T" accounts={accounts} onClose={onClose} />)
    await screen.findByRole('dialog')
    await userEvent.keyboard('{Escape}')
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('does not close when the person clicks outside', async () => {
    const onClose = vi.fn()
    render(<CredentialsDialog open title="T" accounts={accounts} onClose={onClose} />)
    const dialog = await screen.findByRole('dialog')
    const backdrop = dialog.closest('.MuiDialog-root')!.querySelector('.MuiBackdrop-root') as HTMLElement
    await userEvent.click(backdrop)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('closes only through its own button', async () => {
    const onClose = vi.fn()
    render(<CredentialsDialog open title="T" accounts={accounts} onClose={onClose} />)
    await userEvent.click(await screen.findByRole('button', { name: 'I have saved them' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Copy all puts every account on the clipboard, one per line', async () => {
    render(<CredentialsDialog open title="T" accounts={accounts} onClose={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Copy all' }))
    expect(writeText).toHaveBeenCalledWith('Ann Lee (manager): al12ab / Pw-One-111\nBo Ray: Pw-Two-222')
  })

  it('copes with a browser that has no clipboard or refuses the copy', async () => {
    writeText.mockRejectedValue(new Error('denied'))
    render(<CredentialsDialog open title="T" accounts={accounts} onClose={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Copy all' }))
    expect(writeText).toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    await userEvent.click(screen.getByRole('button', { name: 'Copy all' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
