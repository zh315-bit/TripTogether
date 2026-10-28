export type RegisterRequest = { username: string; email: string; password: string }
export type LoginRequest = { email: string; password: string }
export type TokenResponse = { access_token: string; token_type: 'bearer' }
export type DemoMember = 'mika' | 'jonas' | 'aiko'
export type DemoTokenResponse = TokenResponse & { member: DemoMember; username: string; trip_id: number }
export type User = { id: number; username: string; email: string; created_at: string }
