export type RegisterRequest = { username: string; email: string; password: string }
export type LoginRequest = { email: string; password: string }
export type TokenResponse = { access_token: string; token_type: 'bearer' }
export type User = { id: number; username: string; email: string; created_at: string }
