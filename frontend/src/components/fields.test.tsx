import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { DateField, NumberField } from './fields'

describe('DateField', () => {
  it('is a required date input with its label kept above the box', () => {
    render(<DateField label="Start date" />)
    const input = screen.getByLabelText(/Start date/)
    expect(input).toHaveAttribute('type', 'date')
    expect(input).toBeRequired()
    expect(screen.getByText('Start date', { selector: 'label' })).toHaveAttribute('data-shrink', 'true')
  })

  it('lets a caller make it optional', () => {
    render(<DateField label="Done on" required={false} />)
    expect(screen.getByLabelText('Done on')).not.toBeRequired()
  })

  it('takes a typed date', async () => {
    function Wrapper() {
      const [v, setV] = useState('')
      return <DateField label="Due" value={v} onChange={(e) => setV(e.target.value)} />
    }
    render(<Wrapper />)
    await userEvent.type(screen.getByLabelText(/Due/), '2026-03-09')
    expect(screen.getByLabelText(/Due/)).toHaveValue('2026-03-09')
  })
})

describe('NumberField', () => {
  it('is a number input that refuses negatives and allows decimals', () => {
    render(<NumberField label="Hourly cost" />)
    const input = screen.getByLabelText('Hourly cost')
    expect(input).toHaveAttribute('type', 'number')
    expect(input).toHaveAttribute('min', '0')
    expect(input).toHaveAttribute('step', 'any')
  })

  it('reports what the person typed', async () => {
    const onChange = vi.fn()
    render(<NumberField label="Hours" onChange={onChange} />)
    await userEvent.type(screen.getByLabelText('Hours'), '12.5')
    expect(onChange).toHaveBeenCalled()
    expect(screen.getByLabelText('Hours')).toHaveValue(12.5)
  })
})
