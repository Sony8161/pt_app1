import { RISK_COLOR, RISK_LABEL, hours, percent, todayIso } from './format'

describe('format (more)', () => {
  it('writes hours with a thousands separator and no decimals', () => {
    expect(hours(0)).toBe('0 h')
    expect(hours(1234.6)).toBe('1,235 h')
  })

  it('keeps 0 percent as a real value but dashes out a missing one', () => {
    expect(percent(0)).toBe('0%')
    expect(percent(undefined)).toBe('—')
    expect(percent(99.5)).toBe('100%')
  })

  it('gives every risk level a readable word and a chip colour', () => {
    expect(RISK_LABEL).toEqual({ on_track: 'On track', at_risk: 'At risk', overdue: 'Overdue', done: 'Done' })
    expect(RISK_COLOR).toEqual({ on_track: 'success', at_risk: 'warning', overdue: 'error', done: 'default' })
  })

  describe('todayIso', () => {
    afterEach(() => vi.useRealTimers())

    it('is the local calendar day as YYYY-MM-DD, zero padded', () => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(2026, 2, 9, 12, 0, 0))
      expect(todayIso()).toBe('2026-03-09')
    })

    it('moves by whole days, across month and year ends', () => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(2026, 11, 31, 12, 0, 0))
      expect(todayIso(1)).toBe('2027-01-01')
      expect(todayIso(-31)).toBe('2026-11-30')
    })
  })
})
