import { render, screen } from '@testing-library/react'
import { PageHeader } from './PageHeader'

describe('PageHeader', () => {
  it('has the title as the page heading', () => {
    render(<PageHeader title="People" />)
    expect(screen.getByRole('heading', { level: 1, name: 'People' })).toBeInTheDocument()
  })

  it('shows the subtitle and the action buttons when given', () => {
    render(<PageHeader title="People" subtitle={<em>Everyone</em>} actions={<button>New person</button>} />)
    expect(screen.getByText('Everyone')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New person' })).toBeInTheDocument()
  })

  it('leaves out the empty parts', () => {
    const { container } = render(<PageHeader title="Archive" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(container.querySelectorAll('.MuiTypography-root')).toHaveLength(1)
  })
})
