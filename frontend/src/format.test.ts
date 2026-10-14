import { dateRange, formatDate, money, percent } from './format'

describe('format', () => {
  it('hides money the server did not send', () => {
    expect(money(null)).toBe('—')
    expect(money(61168)).toBe('$61,168')
  })

  it('shows a calendar date without any time zone shift', () => {
    expect(formatDate('2026-03-09')).toBe('Mar 9, 2026')
    expect(dateRange('2026-03-09', '2026-03-20')).toBe('Mar 9, 2026 to Mar 20, 2026')
  })

  it('rounds percentages and handles missing ones', () => {
    expect(percent(33.3)).toBe('33%')
    expect(percent(null)).toBe('—')
  })
})
