import type { CategoryRulesData, ExpensesResponse, IncomeResponse } from '../types/budget'
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

