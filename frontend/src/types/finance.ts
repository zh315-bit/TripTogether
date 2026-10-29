import type { AuthenticatedRequest } from './trip'

/** equal: same share each; shares: by weight; exact: amounts typed in. */
export type SplitMethod = 'equal' | 'shares' | 'exact'

export type ExpenseSplit = {
  user_id: number
  share_amount: string
  /** Set only for `shares` splits. */
  weight: number | null
}

/** One participant's part of a request: a weight for `shares`, an amount for `exact`. */
export type SplitInput = {
  user_id: number
  weight?: number
  amount?: string
}

export type Expense = {
  id: number
  trip_id: number
  description: string
  amount: string
  currency: string
  paid_by_user_id: number
  expense_date: string
  split_method: SplitMethod
  created_by_user_id: number
  version: number
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
  split_method: SplitMethod
  /** For `equal`. */
  participant_user_ids?: number[]
  /** For `shares` and `exact`. */
  splits?: SplitInput[]
}

export type MemberBalance = {
  user_id: number
  username: string
  paid: string
  share: string
  /** Net of recorded payments: positive when the member paid others more than they received. */
  settled: string
  balance: string
}

export type Settlement = {
  id: number
  trip_id: number
  from_user_id: number
  to_user_id: number
  amount: string
  currency: string
  paid_on: string
  note: string | null
  recorded_by_user_id: number
  created_at: string
}

export type SettlementInput = {
  from_user_id: number
  to_user_id: number
  amount: string
  currency: string
  paid_on: string
  note?: string
}

export type SettlementSuggestion = {
  from_user_id: number
  to_user_id: number
  amount: string
}

export type SettlementSummary = {
  transfers: number
  unsettled_members: number
  /** True when the transfer count is provably the fewest possible. */
  minimal: boolean
}

export type Balance = {
  trip_id: number
  currency: string | null
  members: MemberBalance[]
  suggested_settlements: SettlementSuggestion[]
  settlement: SettlementSummary
}

export type { AuthenticatedRequest }
