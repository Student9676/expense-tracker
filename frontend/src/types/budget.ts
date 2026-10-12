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
  custom_id?: string
  name: string
  merchant_name?: string | null
  amount: number
  amount_cents?: number | null
  date?: string | null
  category: string
  excluded: boolean
  is_custom: boolean
  is_recurring: boolean
  pfc_primary?: string | null
  pfc_detailed?: string | null
}

export interface ExpensesResponse {
  expenses: ExpenseItem[]
  total_expenses: number
  total_all: number
  income: number
  leftover: number
  count: number
  excluded_count: number
  month: string
  available_months: string[]
}

export interface IncomeResponse {
  month: string | null
  income: number
  updated_at: string | null
}

export interface CustomExpenseInput {
  name: string
  amount: number
  category?: string
  date?: string
  month?: string
  is_recurring?: boolean
}

export interface RefreshTransactionsResult {
  status: string
  start_date: string
  end_date: string
  save_result: {
    fetched: number
    inserted: number
    updated: number
    skipped: number
    pending_removed: number
    total_in_database: number
  }
}
