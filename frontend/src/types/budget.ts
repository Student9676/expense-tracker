export interface CategoryRule {
  pattern: string
  category: string
  match_type?: 'contains' | 'exact' | 'starts_with' | 'regex'
}

export interface CategoryRulesData {
  rules: CategoryRule[]
  default_category: string
}

export interface ExpenseItem {
  transaction_id: string
  name: string
  merchant_name?: string | null
  amount: number
  amount_cents?: number | null
  date?: string | null
  category: string
  pfc_primary?: string | null
  pfc_detailed?: string | null
}

export interface ExpensesResponse {
  expenses: ExpenseItem[]
  total_expenses: number
  income: number
  leftover: number
  count: number
  month: string
  available_months: string[]
}

export interface IncomeResponse {
  month: string | null
  income: number
  updated_at: string | null
}

