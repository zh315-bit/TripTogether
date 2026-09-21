import { ApiError } from './client'
import type {
  AuthenticatedRequest, Balance, Expense, ExpenseInput, ExpenseSplit,
  MemberBalance, SettlementSuggestion,
} from '../types/finance'

function object(body: unknown): Record<string, unknown> {
  if (typeof body !== 'object' || body === null) {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected finance response.')
  }
  return body as Record<string, unknown>
}

function text(value: unknown, field: string): string {
  if (typeof value !== 'string') {
    throw new ApiError(200, 'INVALID_RESPONSE', `Unexpected finance field: ${field}.`)
  }
  return value
}

function number(value: unknown, field: string): number {
  if (typeof value !== 'number') {
    throw new ApiError(200, 'INVALID_RESPONSE', `Unexpected finance field: ${field}.`)
  }
  return value
}

function money(value: unknown, field: string, signed = false): string {
  const result = text(value, field)
  if (!(signed ? /^-?[0-9]+\.[0-9]{2}$/ : /^[0-9]+\.[0-9]{2}$/).test(result)) {
    throw new ApiError(200, 'INVALID_RESPONSE', `Unexpected money field: ${field}.`)
  }
  return result
}

function parseSplit(body: unknown): ExpenseSplit {
  const value = object(body)
  return {
    user_id: number(value.user_id, 'user_id'),
    share_amount: money(value.share_amount, 'share_amount'),
  }
}

function parseExpense(body: unknown): Expense {
  const value = object(body)
  if (!Array.isArray(value.splits)) {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected expense splits response.')
  }
  return {
    id: number(value.id, 'id'),
    trip_id: number(value.trip_id, 'trip_id'),
    description: text(value.description, 'description'),
    amount: money(value.amount, 'amount'),
    currency: text(value.currency, 'currency'),
    paid_by_user_id: number(value.paid_by_user_id, 'paid_by_user_id'),
    expense_date: text(value.expense_date, 'expense_date'),
    created_by_user_id: number(value.created_by_user_id, 'created_by_user_id'),
    created_at: text(value.created_at, 'created_at'),
    updated_at: text(value.updated_at, 'updated_at'),
    splits: value.splits.map(parseSplit),
  }
}

function parseMemberBalance(body: unknown): MemberBalance {
  const value = object(body)
  return {
    user_id: number(value.user_id, 'user_id'),
    username: text(value.username, 'username'),
    paid: money(value.paid, 'paid'),
    share: money(value.share, 'share'),
    balance: money(value.balance, 'balance', true),
  }
}

function parseSettlement(body: unknown): SettlementSuggestion {
  const value = object(body)
  return {
    from_user_id: number(value.from_user_id, 'from_user_id'),
    to_user_id: number(value.to_user_id, 'to_user_id'),
    amount: money(value.amount, 'amount'),
  }
}

function parseList<T>(body: unknown, parse: (value: unknown) => T, label: string): T[] {
  if (!Array.isArray(body)) {
    throw new ApiError(200, 'INVALID_RESPONSE', `Unexpected ${label} response.`)
  }
  return body.map(parse)
}

function parseBalance(body: unknown): Balance {
  const value = object(body)
  if (!Array.isArray(value.members) || !Array.isArray(value.suggested_settlements)) {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected balance response.')
  }
  return {
    trip_id: number(value.trip_id, 'trip_id'),
    currency: value.currency === null ? null : text(value.currency, 'currency'),
    members: value.members.map(parseMemberBalance),
    suggested_settlements: value.suggested_settlements.map(parseSettlement),
  }
}

export async function listExpenses(
  request: AuthenticatedRequest, tripId: string,
): Promise<Expense[]> {
  return parseList(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/expenses`,
  ), parseExpense, 'expenses')
}

export async function createExpense(
  request: AuthenticatedRequest, tripId: string, payload: ExpenseInput,
): Promise<Expense> {
  return parseExpense(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/expenses`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  ))
}

export async function updateExpense(
  request: AuthenticatedRequest, tripId: string, expenseId: number, payload: ExpenseInput,
): Promise<Expense> {
  return parseExpense(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/expenses/${expenseId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  ))
}

export function deleteExpense(
  request: AuthenticatedRequest, tripId: string, expenseId: number,
): Promise<void> {
  return request<void>(`/api/v1/trips/${encodeURIComponent(tripId)}/expenses/${expenseId}`, {
    method: 'DELETE',
  })
}

export async function getBalance(
  request: AuthenticatedRequest, tripId: string,
): Promise<Balance> {
  return parseBalance(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/balances`,
  ))
}
