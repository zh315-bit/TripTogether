import { ApiError } from './client'
import { ifMatch } from './trips'
import type {
  AuthenticatedRequest, Balance, Expense, ExpenseInput, ExpenseSplit,
  MemberBalance, Settlement, SettlementInput, SettlementSuggestion, SettlementSummary, SplitMethod,
} from '../types/finance'

const SPLIT_METHODS: readonly SplitMethod[] = ['equal', 'shares', 'exact']

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

function splitMethod(value: unknown): SplitMethod {
  if (!SPLIT_METHODS.includes(value as SplitMethod)) {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected finance field: split_method.')
  }
  return value as SplitMethod
}

function parseSplit(body: unknown): ExpenseSplit {
  const value = object(body)
  return {
    user_id: number(value.user_id, 'user_id'),
    share_amount: money(value.share_amount, 'share_amount'),
    weight: value.weight === null || value.weight === undefined ? null : number(value.weight, 'weight'),
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
    split_method: splitMethod(value.split_method),
    created_by_user_id: number(value.created_by_user_id, 'created_by_user_id'),
    version: number(value.version, 'version'),
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
    settled: money(value.settled, 'settled', true),
    balance: money(value.balance, 'balance', true),
  }
}

function parseSettlementRecord(body: unknown): Settlement {
  const value = object(body)
  return {
    id: number(value.id, 'id'),
    trip_id: number(value.trip_id, 'trip_id'),
    from_user_id: number(value.from_user_id, 'from_user_id'),
    to_user_id: number(value.to_user_id, 'to_user_id'),
    amount: money(value.amount, 'amount'),
    currency: text(value.currency, 'currency'),
    paid_on: text(value.paid_on, 'paid_on'),
    note: value.note === null ? null : text(value.note, 'note'),
    recorded_by_user_id: number(value.recorded_by_user_id, 'recorded_by_user_id'),
    created_at: text(value.created_at, 'created_at'),
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

function parseSettlementSummary(body: unknown): SettlementSummary {
  const value = object(body)
  if (typeof value.minimal !== 'boolean') {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected finance field: minimal.')
  }
  return {
    transfers: number(value.transfers, 'transfers'),
    unsettled_members: number(value.unsettled_members, 'unsettled_members'),
    minimal: value.minimal,
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
    settlement: parseSettlementSummary(value.settlement),
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
  version?: number,
): Promise<Expense> {
  return parseExpense(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/expenses/${expenseId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...ifMatch(version) },
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

export async function listSettlements(request: AuthenticatedRequest, tripId: string): Promise<Settlement[]> {
  return parseList(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/settlements`), parseSettlementRecord, 'settlements')
}

export async function recordSettlement(
  request: AuthenticatedRequest, tripId: string, payload: SettlementInput,
): Promise<Settlement> {
  return parseSettlementRecord(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/settlements`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
  ))
}

export function deleteSettlement(request: AuthenticatedRequest, tripId: string, id: number): Promise<void> {
  return request<void>(`/api/v1/trips/${encodeURIComponent(tripId)}/settlements/${id}`, { method: 'DELETE' })
}

export async function getBalance(
  request: AuthenticatedRequest, tripId: string,
): Promise<Balance> {
  return parseBalance(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/balances`,
  ))
}
