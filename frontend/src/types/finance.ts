import type { AuthenticatedRequest } from './trip'

export type ExpenseSplit = {
  user_id: number
  share_amount: string
}

export type Expense = {
  id: number
  trip_id: number
  description: string
  amount: string
  currency: string
  paid_by_user_id: number
  expense_date: string
  created_by_user_id: number
  created_at: string
  updated_at: string
  splits: ExpenseSplit[]
}

export type ExpenseInput = {
  description: string
  amount: string
  currency: string
  paid_by_user_id: number
  expense_date: string
  participant_user_ids: number[]
}

export type MemberBalance = {
  user_id: number
  username: string
  paid: string
  share: string
  balance: string
}

export type SettlementSuggestion = {
  from_user_id: number
  to_user_id: number
  amount: string
}

export type Balance = {
  trip_id: number
  currency: string | null
  members: MemberBalance[]
  suggested_settlements: SettlementSuggestion[]
}

export type { AuthenticatedRequest }
