import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CategoryRulesData, ExpenseItem } from '../types/budget'
import {
  downloadCategoryRulesFile,
  getCategoryRules,
  getExpenses,
  getIncome,
  saveIncome,
} from '../api/budget'
import { CategoryRulesModal } from './CategoryRulesModal'

function formatCurrency(val: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val)
}

function formatMonthLabel(m: string): string {
  if (!m || m.toLowerCase() === 'all') return 'All Months'
  const parts = m.split('-')
  if (parts.length === 2) {
    const year = Number(parts[0])
    const monthIndex = Number(parts[1]) - 1
    const date = new Date(year, monthIndex, 1)
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
    }
  }
  return m
}

export function BudgetPage() {
  const [selectedMonth, setSelectedMonth] = useState<string>('2026-10')
  const [availableMonths, setAvailableMonths] = useState<string[]>([])
  const [expensesOnly, setExpensesOnly] = useState<boolean>(true)

  // Income state
  const [incomeInput, setIncomeInput] = useState<string>('')
  const [savedIncome, setSavedIncome] = useState<number>(0)
  const [incomeStatus, setIncomeStatus] = useState<string | null>(null)
  const [incomeSaving, setIncomeSaving] = useState(false)

  // Expenses state
  const [expenses, setExpenses] = useState<ExpenseItem[]>([])
  const [loadingExpenses, setLoadingExpenses] = useState(true)
  const [expensesError, setExpensesError] = useState<string | null>(null)

  // Filtering state
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('ALL')

  // Rules state
  const [rulesData, setRulesData] = useState<CategoryRulesData | null>(null)
  const [isRulesModalOpen, setIsRulesModalOpen] = useState(false)

  // Load rules
  const refreshRules = useCallback(async () => {
    try {
      const data = await getCategoryRules()
      setRulesData(data)
    } catch (err) {
      console.error('Failed to load category rules:', err)
    }
  }, [])

  // Load expenses and income when month or expensesOnly changes
  useEffect(() => {
    let ignore = false


    Promise.all([
      getCategoryRules(),
      getIncome(selectedMonth),
      getExpenses(selectedMonth, expensesOnly),
    ])
      .then(([rules, inc, exp]) => {
        if (ignore) return
        setRulesData(rules)
        setSavedIncome(inc.income)
        setIncomeInput(inc.income > 0 ? inc.income.toFixed(2) : '')
        setExpenses(exp.expenses)
        if (exp.available_months && exp.available_months.length > 0) {
          setAvailableMonths(exp.available_months)
        }
        setExpensesError(null)
      })
      .catch((err) => {
        if (ignore) return
        setExpensesError(err instanceof Error ? err.message : 'Failed to fetch data')
      })
      .finally(() => {
        if (!ignore) {
          setLoadingExpenses(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [selectedMonth, expensesOnly])

  const refreshExpenses = useCallback(async () => {
    setLoadingExpenses(true)
    try {
      const exp = await getExpenses(selectedMonth, expensesOnly)
      setExpenses(exp.expenses)
      if (exp.available_months && exp.available_months.length > 0) {
        setAvailableMonths(exp.available_months)
      }
    } catch (err) {
      setExpensesError(err instanceof Error ? err.message : 'Failed to reload expenses')
    } finally {
      setLoadingExpenses(false)
    }
  }, [selectedMonth, expensesOnly])


  // Save Income handler
  const handleSaveIncome = async () => {
    const parsed = Number.parseFloat(incomeInput.replace(/[^0-9.]/g, ''))
    if (Number.isNaN(parsed) || parsed < 0) {
      setIncomeStatus('Please enter a valid positive number for income.')
      return
    }

    setIncomeSaving(true)
    setIncomeStatus(null)
    try {
      const res = await saveIncome(parsed, selectedMonth)
      setSavedIncome(res.income)
      setIncomeStatus(`Saved ${formatCurrency(res.income)} to database successfully!`)
      // Reload expenses to update server-computed leftover
      refreshExpenses()
    } catch (err) {
      setIncomeStatus(err instanceof Error ? err.message : 'Failed to save income to database.')
    } finally {
      setIncomeSaving(false)
    }
  }

  // Handle rules updated
  const handleRulesSaved = (newData: CategoryRulesData) => {
    setRulesData(newData)
    refreshRules()
    refreshExpenses()
  }

  // Handle month change
  const handleMonthChange = (newMonth: string) => {
    setLoadingExpenses(true)
    setSelectedMonth(newMonth)
  }



  // Filtered expenses based on search and category filter
  const filteredExpenses = useMemo(() => {
    return expenses.filter((item) => {
      const matchesSearch =
        searchQuery === '' ||
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (item.merchant_name && item.merchant_name.toLowerCase().includes(searchQuery.toLowerCase()))
      const matchesCategory =
        categoryFilter === 'ALL' || item.category === categoryFilter
      return matchesSearch && matchesCategory
    })
  }, [expenses, searchQuery, categoryFilter])

  // Computed totals for displayed table
  const totalExpenses = useMemo(() => {
    return filteredExpenses.reduce((sum, item) => sum + (item.amount || 0), 0)
  }, [filteredExpenses])

  // Effective income: what is currently typed if valid, or savedIncome
  const effectiveIncome = useMemo(() => {
    const parsed = Number.parseFloat(incomeInput.replace(/[^0-9.]/g, ''))
    return !Number.isNaN(parsed) && parsed >= 0 ? parsed : savedIncome
  }, [incomeInput, savedIncome])

  const leftover = useMemo(() => {
    return effectiveIncome - totalExpenses
  }, [effectiveIncome, totalExpenses])

  // Unique categories in current transactions
  const uniqueCategories = useMemo(() => {
    const set = new Set<string>()
    for (const exp of expenses) {
      if (exp.category) set.add(exp.category)
    }
    return Array.from(set).sort()
  }, [expenses])

  return (
    <div className="budget-page">
      <section className="intro">
        <p className="eyebrow">Monthly Budget & Expenses</p>
        <h2>Income & Expenses</h2>
        <p className="lede">
          Set your monthly income, classify expenses using rule-based pattern matching, and monitor your remaining balance.
        </p>
      </section>

      {/* Top Metrics Row */}
      <section className="budget-metrics-grid" aria-label="Budget summary">
        <div className="metric-card metric-card--income">
          <span className="metric-label">Monthly Income</span>
          <span className="metric-value">{formatCurrency(effectiveIncome)}</span>
          <span className="metric-sub">
            {savedIncome > 0 ? `Saved in DB: ${formatCurrency(savedIncome)}` : 'Not yet saved to DB'}
          </span>
        </div>

        <div className="metric-card metric-card--expenses">
          <span className="metric-label">Total Expenses</span>
          <span className="metric-value">{formatCurrency(totalExpenses)}</span>
          <span className="metric-sub">{filteredExpenses.length} transactions in table</span>
        </div>

        <div
          className={`metric-card metric-card--leftover ${
            leftover >= 0 ? 'metric-card--surplus' : 'metric-card--deficit'
          }`}
        >
          <span className="metric-label">Leftover (Income − Expenses)</span>
          <span className="metric-value">{formatCurrency(leftover)}</span>
          <span className="metric-sub">
            {leftover >= 0 ? '✓ Net savings remaining' : '⚠ Expenses exceed income'}
          </span>
        </div>
      </section>

      {/* Income Input Section */}
      <section className="workspace income-panel" aria-label="Monthly income settings">
        <div className="panel-body">
          <div className="section-heading">
            <span className="section-number">01</span>
            <h3>Monthly Income</h3>
          </div>
          <p className="token-note">
            Enter your monthly income. It will be stored by the server in SQLite and used to calculate your leftover budget.
          </p>

          <div className="income-form-row">
            <label className="field month-field">
              <span>Selected Month</span>
              <select
                value={selectedMonth}
                onChange={(e) => handleMonthChange(e.target.value)}
              >
                {availableMonths.map((m) => (
                  <option key={m} value={m}>
                    {formatMonthLabel(m)}
                  </option>
                ))}
                <option value="all">All Months (Overall)</option>
              </select>
            </label>

            <label className="field income-input-field">
              <span>Monthly Income Amount ($)</span>
              <div className="currency-input-wrap">
                <span className="currency-symbol">$</span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="5000.00"
                  value={incomeInput}
                  onChange={(e) => setIncomeInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSaveIncome()
                  }}
                />
              </div>
            </label>

            <div className="income-btn-wrap">
              <button
                type="button"
                className="save-income-btn"
                onClick={handleSaveIncome}
                disabled={incomeSaving || !incomeInput.trim()}
              >
                {incomeSaving ? 'Saving…' : 'Save Income to DB'}
              </button>
            </div>
          </div>

          {incomeStatus && (
            <p
              className={`feedback ${
                incomeStatus.includes('Saved')
                  ? 'feedback--success'
                  : 'feedback--error'
              }`}
              role="status"
            >
              {incomeStatus}
            </p>
          )}
        </div>
      </section>

      {/* Rules Toolbar */}
      <section className="rules-bar">
        <div className="rules-bar-info">
          <span className="rules-badge">
            📁 category_rules.json
          </span>
          <span className="rules-count-text">
            {rulesData?.rules.length ?? 0} active classification rules
          </span>
        </div>

        <div className="rules-bar-actions">
          <button
            type="button"
            className="rules-action-btn"
            onClick={() => setIsRulesModalOpen(true)}
            title="Edit rule patterns and categories"
          >
            ⚙ Edit Category Rules
          </button>
          <button
            type="button"
            className="rules-action-btn rules-action-btn--secondary"
            onClick={() => downloadCategoryRulesFile(rulesData || undefined)}
            title="Download the rules file as category_rules.json"
          >
            ↓ Export Rules File
          </button>
        </div>
      </section>

      {/* Expenses Table Section */}
      <section className="workspace expenses-workspace" aria-label="Expenses table">
        <div className="panel-body">
          <div className="expenses-table-header">
            <div className="section-heading">
              <span className="section-number">02</span>
              <h3>Expenses Table</h3>
            </div>

            <div className="expenses-filter-controls">
              <input
                type="text"
                className="search-input"
                placeholder="Search expense names…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />

              <select
                className="category-filter-select"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                <option value="ALL">All Categories ({uniqueCategories.length})</option>
                {uniqueCategories.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>

              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={expensesOnly}
                  onChange={(e) => {
                    setLoadingExpenses(true)
                    setExpensesOnly(e.target.checked)
                  }}
                />
                <span>Expenses only (&gt; $0)</span>
              </label>
            </div>
          </div>

          {loadingExpenses && (
            <p className="loading-state">Loading expenses from database…</p>
          )}

          {expensesError && (
            <p className="feedback feedback--error" role="alert">
              {expensesError}
            </p>
          )}

          {!loadingExpenses && (
            <div className="table-responsive">
              <table className="expenses-table">
                <thead>
                  <tr>
                    <th className="col-date">Date</th>
                    <th className="col-name">Expense Name</th>
                    <th className="col-category">Category</th>
                    <th className="col-amount">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredExpenses.map((item) => (
                    <tr key={item.transaction_id}>
                      <td className="col-date">{item.date || '—'}</td>
                      <td className="col-name">
                        <span className="expense-title">{item.name}</span>
                        {item.merchant_name && item.merchant_name !== item.name && (
                          <span className="expense-sub">{item.merchant_name}</span>
                        )}
                      </td>
                      <td className="col-category">
                        <span className={`category-tag category-tag--${item.category.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}>
                          {item.category}
                        </span>
                      </td>
                      <td className="col-amount">
                        <span
                          className={`amount-text ${
                            item.amount < 0 ? 'amount-text--credit' : ''
                          }`}
                        >
                          {formatCurrency(item.amount)}
                        </span>
                      </td>
                    </tr>
                  ))}

                  {filteredExpenses.length === 0 && (
                    <tr>
                      <td colSpan={4} className="empty-table-cell">
                        No expenses match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
                <tfoot>
                  <tr className="tfoot-row tfoot-row--expenses">
                    <td colSpan={3} className="tfoot-label">
                      Total Expenses
                    </td>
                    <td className="tfoot-value">{formatCurrency(totalExpenses)}</td>
                  </tr>
                  <tr className="tfoot-row tfoot-row--income">
                    <td colSpan={3} className="tfoot-label">
                      Monthly Income
                    </td>
                    <td className="tfoot-value">{formatCurrency(effectiveIncome)}</td>
                  </tr>
                  <tr
                    className={`tfoot-row tfoot-row--leftover ${
                      leftover >= 0 ? 'tfoot-row--surplus' : 'tfoot-row--deficit'
                    }`}
                  >
                    <td colSpan={3} className="tfoot-label">
                      <strong>Leftover (Income − Total Expenses)</strong>
                    </td>
                    <td className="tfoot-value">
                      <strong>{formatCurrency(leftover)}</strong>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Category Rules Modal */}
      {rulesData && (
        <CategoryRulesModal
          isOpen={isRulesModalOpen}
          initialData={rulesData}
          onClose={() => setIsRulesModalOpen(false)}
          onSaved={handleRulesSaved}
        />
      )}
    </div>
  )
}
