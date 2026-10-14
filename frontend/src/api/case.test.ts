import { keysToCamel, keysToSnake } from './case'

describe('case conversion', () => {
  it('turns API snake_case into camelCase, including nested lists', () => {
    const out = keysToCamel<{ riskLevel: string; items: { dueDate: string }[] }>({ risk_level: 'at_risk', items: [{ due_date: '2026-03-20' }] })
    expect(out).toEqual({ riskLevel: 'at_risk', items: [{ dueDate: '2026-03-20' }] })
  })

  it('leaves values alone: only keys change', () => {
    expect(keysToCamel({ risk_reasons: ['past_due_date'] })).toEqual({ riskReasons: ['past_due_date'] })
  })

  it('turns request camelCase into snake_case for the API', () => {
    expect(keysToSnake({ managerId: 'abc', allocatedHours: 8, startDate: undefined })).toEqual({ manager_id: 'abc', allocated_hours: 8, start_date: undefined })
  })

  it('passes null and primitives through', () => {
    expect(keysToCamel(null)).toBeNull()
    expect(keysToSnake(5)).toBe(5)
  })
})
