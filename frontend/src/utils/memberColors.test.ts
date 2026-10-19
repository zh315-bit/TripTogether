import { describe, expect, it } from 'vitest'
import { MEMBER_PALETTE, UNKNOWN_MEMBER_COLOR, memberStyle, memberStyles } from './memberColors'
import type { TripMember } from '../types/collaboration'

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((index) => {
    const channel = parseInt(hex.slice(index, index + 2), 16) / 255
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (light + 0.05) / (dark + 0.05)
}

const member = (user_id: number, username: string): TripMember => ({
  user_id, username, email: `${username}@example.com`, role: 'member', joined_at: '2026-09-20T00:00:00Z',
})

describe('member colours', () => {
  it.each([...MEMBER_PALETTE, UNKNOWN_MEMBER_COLOR])('%s has enough contrast on light and dark', (color) => {
    expect(contrast(color, '#ffffff')).toBeGreaterThanOrEqual(4.5)
    expect(contrast(color, '#17233a')).toBeGreaterThanOrEqual(3)
  })

  it('is distinct for the first eight members', () => {
    expect(new Set(MEMBER_PALETTE).size).toBe(MEMBER_PALETTE.length)
  })

  it('follows member-list order, so each person keeps one colour', () => {
    const members = [member(7, 'alice'), member(3, 'bob'), member(9, ' carol')]
    const styles = memberStyles(members)
    expect(memberStyle(styles, 7)).toEqual({ color: MEMBER_PALETTE[0], initial: 'A', name: 'alice' })
    expect(memberStyle(styles, 3).color).toBe(MEMBER_PALETTE[1])
    expect(memberStyle(styles, 9).initial).toBe('C')
    // Recomputing from the same list (another page) gives the same result.
    expect(memberStyles([...members])).toEqual(styles)
  })

  it('wraps after the palette and handles unknown proposers', () => {
    const many = Array.from({ length: 10 }, (_, index) => member(index + 1, `m${index}`))
    expect(memberStyle(memberStyles(many), 9).color).toBe(MEMBER_PALETTE[0])
    expect(memberStyle(memberStyles([]), 42)).toEqual({
      color: UNKNOWN_MEMBER_COLOR, initial: '?', name: 'Unknown member',
    })
  })
})
