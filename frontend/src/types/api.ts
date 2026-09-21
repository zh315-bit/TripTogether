export type HealthResponse = {
  status: 'ok'
}

export type ApiValidationIssue = {
  loc: Array<string | number>
  msg: string
  type: string
}

export type ApiErrorPayload = {
  error: {
    code: string
    message: string
    details: ApiValidationIssue[]
  }
}
