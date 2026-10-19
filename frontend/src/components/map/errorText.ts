import { ApiError } from '../../api/client'

/** Prefer the server's field reason (e.g. the 50-item optimize cap) over the generic message. */
export function errorText(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback
  if (error.code === 'VALIDATION_ERROR' && error.details.length > 0) {
    return error.details.map((issue) => issue.msg).join(' ')
  }
  return error.message || fallback
}

export function errorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.code : null
}
