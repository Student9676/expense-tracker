import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  LuCircleCheck,
  LuDownload,
  LuFileJson,
  LuPencil,
  LuPlus,
  LuRefreshCw,
  LuSettings,
  LuTrash2,
  LuTriangleAlert,
} from 'react-icons/lu'
import type { CategoryRulesData, CategorySummaryResponse, ExpenseItem } from '../types/budget'
import {
  deleteCustomExpense,
  downloadCategoryRulesFile,
  getCategoryRules,
  getCategorySummary,
  getExpenses,
  getIncome,
  refreshPast3Months,
  saveIncome,
  toggleTransactionExclusion,
  updateCustomExpense,
} from '../api/budget'
import { AddCustomExpenseModal } from './AddCustomExpenseModal'
import { CategoryPieChart } from './CategoryPieChart'
import { CategoryRulesModal } from './CategoryRulesModal'
import { EditCustomExpenseModal } from './EditCustomExpenseModal'
import { MonthStepper } from './MonthStepper'
import { formatCurrency, formatMonthLabel } from '../utils/format'

/** True once the launch-time refresh has started (persists across BudgetPage remounts). */
let hasAutoRefreshed = false

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

  // Custom Expense Modal state
  const [isAddCustomModalOpen, setIsAddCustomModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<ExpenseItem | null>(null)

  // Refresh past 3 months state
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null)
  const [refreshError, setRefreshError] = useState<string | null>(null)

  // Autosave status state
  const [autosaveStatus, setAutosaveStatus] = useState<string | null>(null)

  // Server-side category grouping (pie chart + totals table).
  // Results are tagged with the request key so "loading" is derived, and the
  // previous result stays visible while a new one is fetched.
  const [summaryVersion, setSummaryVersion] = useState(0)
  const [summaryResult, setSummaryResult] = useState<{
    key: string
    data: CategorySummaryResponse
  } | null>(null)
  const [summaryFailure, setSummaryFailure] = useState<{ key: string; message: string } | null>(
    null,
  )
  const summaryKey = `${selectedMonth}|${expensesOnly}|${searchQuery}|${categoryFilter}|${summaryVersion}`
  const summary = summaryResult?.data ?? null
  const summaryError = summaryFailure?.key === summaryKey ? summaryFailure.message : null
  const summaryLoading = summaryResult?.key !== summaryKey && summaryFailure?.key !== summaryKey

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

  // Fetch category totals from the server whenever the table's rows could change
  useEffect(() => {
    let ignore = false
    const key = summaryKey
    // Debounce typing in the search box; other changes fetch immediately.
    const timer = setTimeout(
      () => {
        getCategorySummary({
          month: selectedMonth,
          expensesOnly,
          search: searchQuery,
          category: categoryFilter,
        })
          .then((data) => {
            if (ignore) return
            setSummaryResult({ key, data })
            setSummaryFailure(null)
          })
          .catch((err) => {
            if (ignore) return
            setSummaryFailure({
              key,
              message: err instanceof Error ? err.message : 'Failed to load category totals',
            })
          })
      },
      searchQuery ? 250 : 0,
    )

    return () => {
      ignore = true
      clearTimeout(timer)
    }
  }, [summaryKey, selectedMonth, expensesOnly, searchQuery, categoryFilter])

  const refreshExpenses = useCallback(async () => {
    setLoadingExpenses(true)
    try {
      const exp = await getExpenses(selectedMonth, expensesOnly)
      setExpenses(exp.expenses)
      if (exp.available_months && exp.available_months.length > 0) {
        setAvailableMonths(exp.available_months)
      }
      setSummaryVersion((v) => v + 1)
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

  // Handle transaction exclusion toggle with autosave
  const handleToggleExclusion = async (transactionId: string) => {
    const target = expenses.find((e) => e.transaction_id === transactionId)
    if (!target) return
    const nextExcluded = !target.excluded

    // Optimistically update local state immediately
    setExpenses((prev) =>
      prev.map((e) =>
        e.transaction_id === transactionId ? { ...e, excluded: nextExcluded } : e,
      ),
    )
    setAutosaveStatus('Autosaving preference…')

    try {
      await toggleTransactionExclusion(transactionId, selectedMonth, nextExcluded)
      setSummaryVersion((v) => v + 1)
      setAutosaveStatus('Preference autosaved')
      setTimeout(() => setAutosaveStatus(null), 2500)
    } catch (err) {
      console.error('Failed to autosave exclusion:', err)
      // Revert on failure
      setExpenses((prev) =>
        prev.map((e) =>
          e.transaction_id === transactionId ? { ...e, excluded: !nextExcluded } : e,
        ),
      )
      setAutosaveStatus('Failed to autosave')
    }
  }

  // Handle deleting custom expense
  const handleDeleteCustomExpense = async (customId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm('Delete this custom expense?')) return

    try {
      await deleteCustomExpense(customId)
      setExpenses((prev) =>
        prev.filter((item) => item.transaction_id !== customId && item.custom_id !== customId),
      )
      setSummaryVersion((v) => v + 1)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete custom expense')
    }
  }

  // Handle custom expense created
  const handleCustomExpenseCreated = (item: ExpenseItem) => {
    setExpenses((prev) => [item, ...prev])
    refreshExpenses()
  }

  // Handle custom expense saved (after edit)
  const handleCustomExpenseSaved = (updated: ExpenseItem) => {
    setExpenses((prev) =>
      prev.map((e) =>
        e.custom_id && e.custom_id === updated.custom_id ? { ...e, ...updated } : e,
      ),
    )
    refreshExpenses()
  }

  // Refresh the past 3 months from the bank. `auto` is true for the launch-time run.
  const runRefresh = useCallback(
    async (auto: boolean) => {
      setRefreshing(true)
      setRefreshMessage(null)
      setRefreshError(null)

      try {
        const res = await refreshPast3Months()
        const savedCount = res.save_result.inserted + res.save_result.updated
        setRefreshMessage(
          `${auto ? 'Automatically refreshed' : 'Successfully refreshed'} past 3 months! (${savedCount} transactions updated/inserted, ${res.save_result.total_in_database} total in DB).`,
        )
        await refreshExpenses()
        setTimeout(() => setRefreshMessage(null), 6000)

        // Some banks may have failed (for example a login that needs to be redone).
        const failed = (res.banks ?? []).filter((bank) => bank.status === 'error')
        if (failed.length > 0) {
          setRefreshError(
            `Could not refresh ${failed
              .map((bank) => `${bank.institution_name} (${bank.error ?? 'unknown error'})`)
              .join(', ')}. Other banks were updated.`,
          )
        }
      } catch (err) {
        const detail =
          err instanceof Error
            ? err.message
            : 'Failed to refresh transactions. Please ensure your account is connected in Connection Desk.'
        setRefreshError(auto ? `Automatic refresh failed: ${detail}` : detail)
      } finally {
        setRefreshing(false)
      }
    },
    [refreshExpenses],
  )

  const handleRefreshPast3Months = () => {
    void runRefresh(false)
  }

  // Refresh once when the app launches. The module-level flag keeps it from running again
  // when switching tabs (the page remounts) or when React StrictMode re-runs effects in dev.
  useEffect(() => {
    if (hasAutoRefreshed) return
    hasAutoRefreshed = true
    void runRefresh(true)
  }, [runRefresh])

  // Filtered expenses based on search and category filter
  const filteredExpenses = useMemo(() => {
    return expenses.filter((item) => {
      const matchesSearch =
        searchQuery === '' ||
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (item.merchant_name &&
          item.merchant_name.toLowerCase().includes(searchQuery.toLowerCase()))
      const matchesCategory =
        categoryFilter === 'ALL' || item.category === categoryFilter
      return matchesSearch && matchesCategory
    })
  }, [expenses, searchQuery, categoryFilter])

  // Computed totals for displayed table (excluding unchecked items)
  const totalExpenses = useMemo(() => {
    return filteredExpenses.reduce(
      (sum, item) => sum + (!item.excluded ? (item.amount || 0) : 0),
      0,
    )
  }, [filteredExpenses])

  const totalAllExpenses = useMemo(() => {
    return filteredExpenses.reduce((sum, item) => sum + (item.amount || 0), 0)
  }, [filteredExpenses])

  const excludedCount = useMemo(() => {
    return filteredExpenses.filter((item) => item.excluded).length
  }, [filteredExpenses])

  // Effective income: what is currently typed if valid, or savedIncome
  const effectiveIncome = useMemo(() => {
    const parsed = Number.parseFloat(incomeInput.replace(/[^0-9.]/g, ''))
    return !Number.isNaN(parsed) && parsed >= 0 ? parsed : savedIncome
  }, [incomeInput, savedIncome])

  const leftover = useMemo(() => {
    return effectiveIncome - totalExpenses
  }, [effectiveIncome, totalExpenses])

  // Months for the dropdowns and stepper: newest first, always including the selected month
  const monthOptions = useMemo(() => {
    const set = new Set(availableMonths)
    if (selectedMonth && selectedMonth.toLowerCase() !== 'all') set.add(selectedMonth)
    return Array.from(set).sort((a, b) => b.localeCompare(a))
  }, [availableMonths, selectedMonth])

  // Only label rows with their bank once more than one bank has transactions
  const showBankBadge = useMemo(
    () => new Set(expenses.map((e) => e.institution_name).filter(Boolean)).size > 1,
    [expenses],
  )

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
          Set your monthly income, classify expenses using rule-based pattern matching, exclude one-off transactions, add custom recurring bills, and monitor your remaining balance.
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
          <span className="metric-sub">
            {filteredExpenses.length - excludedCount} included
            {excludedCount > 0 ? ` (${excludedCount} excluded)` : ''}
          </span>
        </div>

        <div
          className={`metric-card metric-card--leftover ${
            leftover >= 0 ? 'metric-card--surplus' : 'metric-card--deficit'
          }`}
        >
          <span className="metric-label">Leftover (Income − Expenses)</span>
          <span className="metric-value">{formatCurrency(leftover)}</span>
          <span className="metric-sub">
            {leftover >= 0 ? (
              <>
                <LuCircleCheck size={14} aria-hidden="true" />
                Net savings remaining
              </>
            ) : (
              <>
                <LuTriangleAlert size={14} aria-hidden="true" />
                Expenses exceed income
              </>
            )}
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
                {monthOptions.map((m) => (
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

      {/* Rules & Sync Toolbar */}
      <section className="rules-bar">
        <div className="rules-bar-info">
          <span className="rules-badge">
            <LuFileJson size={14} aria-hidden="true" />
            category_rules.json
          </span>
          <span className="rules-count-text">
            {rulesData?.rules.length ?? 0} active classification rules
          </span>
          {autosaveStatus && (
            <span className="autosave-indicator" role="status">
              • {autosaveStatus}
            </span>
          )}
        </div>

        <div className="rules-bar-actions">
          <button
            type="button"
            className="rules-action-btn rules-action-btn--refresh"
            onClick={handleRefreshPast3Months}
            disabled={refreshing}
            title="Refresh bank transactions for the past 3 months into the database"
          >
            <LuRefreshCw
              size={15}
              className={refreshing ? 'icon-spin' : undefined}
              aria-hidden="true"
            />
            {refreshing ? 'Refreshing from Bank…' : 'Refresh Past 3 Months'}
          </button>
          <button
            type="button"
            className="rules-action-btn"
            onClick={() => setIsRulesModalOpen(true)}
            title="Edit rule patterns and categories"
          >
            <LuSettings size={15} aria-hidden="true" />
            Edit Category Rules
          </button>
          <button
            type="button"
            className="rules-action-btn rules-action-btn--secondary"
            onClick={() => downloadCategoryRulesFile(rulesData || undefined)}
            title="Download the rules file as category_rules.json"
          >
            <LuDownload size={15} aria-hidden="true" />
            Export Rules File
          </button>
        </div>
      </section>

      {/* Refresh Status Feedback */}
      {refreshMessage && (
        <div className="banner banner--success" role="status">
          <LuCircleCheck size={18} aria-hidden="true" />
          <span>{refreshMessage}</span>
        </div>
      )}
      {refreshError && (
        <div className="banner banner--error" role="alert">
          <LuTriangleAlert size={18} aria-hidden="true" />
          <span>{refreshError}</span>
        </div>
      )}

      {/* Category Chart Section */}
      <section className="workspace chart-workspace" aria-label="Spending by category">
        <div className="panel-body">
          <div className="section-heading">
            <span className="section-number">02</span>
            <h3>Spending by Category</h3>
          </div>
          <p className="table-subtitle">
            {formatMonthLabel(selectedMonth)} · follows the expenses table's filters and
            exclusions.
          </p>
          <CategoryPieChart summary={summary} loading={summaryLoading} error={summaryError} />
        </div>
      </section>

      {/* Expenses Table Section */}
      <section className="workspace expenses-workspace" aria-label="Expenses table">
        <div className="panel-body">
          <div className="expenses-table-header">
            <div>
              <div className="section-heading">
                <span className="section-number">03</span>
                <h3>Expenses Table</h3>
              </div>
              <p className="table-subtitle">
                Uncheck any row to exclude it from this month's calculations (autosaved). Add custom recurring expenses or bills below.
              </p>
            </div>

            <div className="expenses-top-actions">
              <MonthStepper
                months={monthOptions}
                value={selectedMonth}
                onChange={handleMonthChange}
              />
              <button
                type="button"
                className="btn-add-custom"
                onClick={() => setIsAddCustomModalOpen(true)}
              >
                <LuPlus size={16} aria-hidden="true" />
                Add Custom Expense
              </button>
            </div>
          </div>

          <div className="expenses-toolbar-row">
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

            {excludedCount > 0 && (
              <div className="excluded-summary-pill">
                <span>{excludedCount} excluded from calculation</span>
              </div>
            )}
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
                    <th className="col-checkbox" title="Include/Exclude from calculations">
                      Incl.
                    </th>
                    <th className="col-date">Date</th>
                    <th className="col-name">Expense Name</th>
                    <th className="col-category">Category</th>
                    <th className="col-amount">Amount</th>
                    <th className="col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredExpenses.map((item) => (
                    <tr
                      key={item.transaction_id}
                      className={item.excluded ? 'row--excluded' : ''}
                    >
                      <td className="col-checkbox">
                        <label className="checkbox-wrap">
                          <input
                            type="checkbox"
                            checked={!item.excluded}
                            onChange={() => handleToggleExclusion(item.transaction_id)}
                            title={
                              item.excluded
                                ? 'Excluded from total. Click to include.'
                                : 'Included in total. Click to exclude.'
                            }
                            aria-label={`Include ${item.name} in calculation`}
                          />
                        </label>
                      </td>
                      <td className="col-date">{item.date || '—'}</td>
                      <td className="col-name">
                        <div className="name-cell-wrap">
                          <span className="expense-title">{item.name}</span>
                          {item.merchant_name && item.merchant_name !== item.name && (
                            <span className="expense-sub">{item.merchant_name}</span>
                          )}
                          <div className="badges-wrap">
                            {showBankBadge && item.institution_name && (
                              <span className="badge badge--bank">{item.institution_name}</span>
                            )}
                            {item.is_custom && (
                              <span className="badge badge--custom">Custom</span>
                            )}
                            {item.is_recurring && (
                              <span className="badge badge--recurring">Monthly Recurring</span>
                            )}
                            {item.excluded && (
                              <span className="badge badge--excluded">Excluded from Total</span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="col-category">
                        <span
                          className={`category-tag category-tag--${item.category
                            .toLowerCase()
                            .replace(/[^a-z0-9]/g, '-')}`}
                        >
                          {item.category}
                        </span>
                      </td>
                      <td className="col-amount">
                        <span
                          className={`amount-text ${
                            item.amount < 0 ? 'amount-text--credit' : ''
                          } ${item.excluded ? 'amount-text--excluded' : ''}`}
                        >
                          {formatCurrency(item.amount)}
                        </span>
                      </td>
                      <td className="col-actions">
                        {item.is_custom && (
                          <div className="row-actions">
                            <button
                              type="button"
                              className="btn-edit-item"
                              onClick={(e) => {
                                e.stopPropagation()
                                setEditingItem(item)
                              }}
                              title="Edit custom expense"
                              aria-label={`Edit ${item.name}`}
                            >
                              <LuPencil size={16} aria-hidden="true" />
                            </button>
                            <button
                              type="button"
                              className="btn-delete-item"
                              onClick={(e) =>
                                handleDeleteCustomExpense(
                                  item.custom_id || item.transaction_id,
                                  e,
                                )
                              }
                              title="Delete custom expense"
                              aria-label={`Delete ${item.name}`}
                            >
                              <LuTrash2 size={16} aria-hidden="true" />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}

                  {filteredExpenses.length === 0 && (
                    <tr>
                      <td colSpan={6} className="empty-table-cell">
                        No expenses match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
                <tfoot>
                  <tr className="tfoot-row tfoot-row--expenses">
                    <td colSpan={4} className="tfoot-label">
                      Total Expenses {excludedCount > 0 ? `(excl. ${excludedCount} item${excludedCount === 1 ? '' : 's'})` : ''}
                    </td>
                    <td className="tfoot-value">{formatCurrency(totalExpenses)}</td>
                    <td />
                  </tr>
                  {excludedCount > 0 && (
                    <tr className="tfoot-row tfoot-row--subtle">
                      <td colSpan={4} className="tfoot-label">
                        All Transactions Total (before exclusions)
                      </td>
                      <td className="tfoot-value">{formatCurrency(totalAllExpenses)}</td>
                      <td />
                    </tr>
                  )}
                  <tr className="tfoot-row tfoot-row--income">
                    <td colSpan={4} className="tfoot-label">
                      Monthly Income
                    </td>
                    <td className="tfoot-value">{formatCurrency(effectiveIncome)}</td>
                    <td />
                  </tr>
                  <tr
                    className={`tfoot-row tfoot-row--leftover ${
                      leftover >= 0 ? 'tfoot-row--surplus' : 'tfoot-row--deficit'
                    }`}
                  >
                    <td colSpan={4} className="tfoot-label">
                      <strong>Leftover (Income − Total Expenses)</strong>
                    </td>
                    <td className="tfoot-value">
                      <strong>{formatCurrency(leftover)}</strong>
                    </td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Add Custom Expense Modal */}
      <AddCustomExpenseModal
        isOpen={isAddCustomModalOpen}
        defaultMonth={selectedMonth}
        existingCategories={uniqueCategories}
        onClose={() => setIsAddCustomModalOpen(false)}
        onCreated={handleCustomExpenseCreated}
      />

      {/* Edit Custom Expense Modal */}
      <EditCustomExpenseModal
        isOpen={!!editingItem}
        item={editingItem}
        existingCategories={uniqueCategories}
        onClose={() => setEditingItem(null)}
        onSaved={handleCustomExpenseSaved}
      />

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
