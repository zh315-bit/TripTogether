import type { TripMember } from '../types/collaboration'

/**
 * Each colour has at least 4.5:1 contrast with white (the marker initial) and
 * 3:1 with the dark ink #17233a, so markers read on light and dark map tiles.
 * Colour is never the only cue: markers show the member initial and tooltips
 * and lists show the member name.
 */
export const MEMBER_PALETTE = [
  '#1c6fc2', '#d71f1f', '#127f36', '#a25d17', '#9c38e3', '#117a7a', '#cf1e76', '#787011',
] as const

export const UNKNOWN_MEMBER_COLOR = '#676f7b'

export type MemberStyle = { color: string; initial: string; name: string }

/**
 * Colour comes from the member's position in the trip member list, so the same
 * person has the same colour on every page that uses this list.
 */
export function memberStyles(members: TripMember[]): Map<number, MemberStyle> {
  return new Map(members.map((member, index) => [member.user_id, {
    color: MEMBER_PALETTE[index % MEMBER_PALETTE.length],
    initial: (member.username.trim()[0] ?? '?').toUpperCase(),
    name: member.username,
  }]))
}

export function memberStyle(styles: Map<number, MemberStyle>, userId: number): MemberStyle {
  return styles.get(userId) ?? { color: UNKNOWN_MEMBER_COLOR, initial: '?', name: 'Unknown member' }
}
