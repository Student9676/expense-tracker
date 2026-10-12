import type {
  CategoryRulesData,
  CategorySummaryResponse,
  CustomExpenseInput,
  ExpenseItem,
  ExpensesResponse,
  IncomeResponse,
  RefreshTransactionsResult,
} from '../types/budget'
import { request } from './client'

export function getIncome(month?: string): Promise<IncomeResponse> {
  const query = month ? `?month=${encodeURIComponent(month)}` : ''
  return request<IncomeResponse>(`/api/income${query}`)
}

export function saveIncome(income: number, month?: string): Promise<IncomeResponse> {
  return request<IncomeResponse>('/api/income', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ income, month }),
  })
}

export function getCategoryRules(): Promise<CategoryRulesData> {
  return request<CategoryRulesData>('/api/category_rules')
}

export function saveCategoryRules(
  data: CategoryRulesData,
): Promise<{ status: string; count: number; rules: CategoryRulesData['rules']; default_category: string }> {
  return request('/api/category_rules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function getExpenses(
  month?: string,
  expensesOnly = true,
): Promise<ExpensesResponse> {
  const params = new URLSearchParams()
  if (month) params.set('month', month)
  params.set('expenses_only', String(expensesOnly))
  return request<ExpensesResponse>(`/api/expenses?${params.toString()}`)
}

export interface CategorySummaryOptions {
  month?: string
  expensesOnly?: boolean
  search?: string
  /** Category filter; omit or pass 'ALL' for every category. */
  category?: string
}

/** Expense totals grouped by category, computed on the server using the table's filters. */
export function getCategorySummary(
  options: CategorySummaryOptions = {},
): Promise<CategorySummaryResponse> {
  const { month, expensesOnly = true, search, category } = options
  const params = new URLSearchParams()
  if (month) params.set('month', month)
  params.set('expenses_only', String(expensesOnly))
  if (search && search.trim()) params.set('search', search.trim())
  if (category && category !== 'ALL') params.set('category', category)
  return request<CategorySummaryResponse>(`/api/expenses/category_summary?${params.toString()}`)
}

export function toggleTransactionExclusion(
  transactionId: string,
  month: string | null,
  excluded: boolean,
): Promise<{ status: string; transaction_id: string; month: string | null; excluded: boolean }> {
  return request('/api/expenses/toggle_exclusion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transaction_id: transactionId, month, excluded }),
  })
}

export function createCustomExpense(data: CustomExpenseInput): Promise<ExpenseItem> {
  return request<ExpenseItem>('/api/custom_expenses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function deleteCustomExpense(customId: string): Promise<{ status: string; id: string }> {
  return request<{ status: string; id: string }>(`/api/custom_expenses/${encodeURIComponent(customId)}`, {
    method: 'DELETE',
  })
}

export function updateCustomExpense(
  customId: string,
  data: Partial<CustomExpenseInput>,
): Promise<ExpenseItem> {
  return request<ExpenseItem>(`/api/custom_expenses/${encodeURIComponent(customId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function refreshPast3Months(): Promise<RefreshTransactionsResult> {
  return request<RefreshTransactionsResult>('/api/refresh_transactions', {
    method: 'POST',
  })
}

export function downloadCategoryRulesFile(rulesData?: CategoryRulesData): void {
  // If we have the current rules in memory, download as Blob to ensure instant export
  if (rulesData) {
    const blob = new Blob([JSON.stringify(rulesData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'category_rules.json'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } else {
    // Otherwise download from server endpoint
    window.location.href = '/backend/api/category_rules/export'
  }
}
