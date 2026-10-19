import { describe, expect, it } from 'vitest'
import { tripDays } from './days'

describe('tripDays', () => {
  it('lists every day inclusively, across month ends and leap days', () => {
    expect(tripDays('2027-06-10', '2027-06-12')).toEqual(['2027-06-10', '2027-06-11', '2027-06-12'])
    expect(tripDays('2028-02-28', '2028-03-01')).toEqual(['2028-02-28', '2028-02-29', '2028-03-01'])
    expect(tripDays('2027-06-10', '2027-06-10')).toEqual(['2027-06-10'])
  })

  it('returns nothing for a reversed range and caps very long ones', () => {
    expect(tripDays('2027-06-12', '2027-06-10')).toEqual([])
    expect(tripDays('2027-01-01', '2030-01-01')).toHaveLength(366)
  })
})
