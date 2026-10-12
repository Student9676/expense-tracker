import { useState } from 'react'
import type { CustomExpenseInput, ExpenseItem } from '../types/budget'
import { createCustomExpense } from '../api/budget'

interface AddCustomExpenseModalProps {
  isOpen: boolean
  defaultMonth: string
  existingCategories: string[]
  onClose: () => void
  onCreated: (item: ExpenseItem) => void
}

function getDefaultDate(month: string): string {
  if (month && month !== 'all' && /^\d{4}-\d{2}$/.test(month)) {
    return `${month}-01`
  }
  const now = new Date()
  const year = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${year}-${m}-${d}`
}

export function AddCustomExpenseModal({
  isOpen,
  defaultMonth,
  existingCategories,
  onClose,
  onCreated,
}: AddCustomExpenseModalProps) {
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('')
  const [date, setDate] = useState(() => getDefaultDate(defaultMonth))
  const [isRecurring, setIsRecurring] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setErrorMessage('Please enter an expense name')
      return
    }

    const numAmount = Number.parseFloat(amount.replace(/[^0-9.]/g, ''))
    if (Number.isNaN(numAmount) || numAmount <= 0) {
      setErrorMessage('Please enter a valid positive amount')
      return
    }

    setSubmitting(true)
    setErrorMessage(null)

    const payload: CustomExpenseInput = {
      name: name.trim(),
      amount: numAmount,
      category: category.trim() || undefined,
      date: date || undefined,
      month: defaultMonth !== 'all' ? defaultMonth : (date ? date.slice(0, 7) : undefined),
      is_recurring: isRecurring,
    }

    try {
      const created = await createCustomExpense(payload)
      onCreated(created)
      onClose()
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to add custom expense')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="custom-modal-title">
      <div className="modal-window modal-window--compact">
        <header className="modal-header">
          <div>
            <p className="kicker">Custom expense</p>
            <h2 id="custom-modal-title" className="modal-title">Add Custom Expense</h2>
          </div>
          <button
            type="button"
            className="modal-close-button"
            onClick={onClose}
            aria-label="Close modal"
          >
            ✕
          </button>
        </header>

        <form onSubmit={handleSubmit} className="custom-expense-form">
          <div className="modal-content">
            <p className="token-note">
              Add a manual expense not tracked by your bank. You can optionally make it recur every month.
            </p>

            <div className="form-grid">
              <label className="field">
                <span>Expense Name *</span>
                <input
                  type="text"
                  placeholder="e.g. Rent, Gym, Babysitter"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoFocus
                  required
                />
              </label>

              <label className="field">
                <span>Amount ($) *</span>
                <div className="currency-input-wrap">
                  <span className="currency-symbol">$</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder="1200.00"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    required
                  />
                </div>
              </label>

              <label className="field">
                <span>Category (Optional)</span>
                <input
                  type="text"
                  list="category-suggestions"
                  placeholder="e.g. Housing or leave blank for auto-rules"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                />
                <datalist id="category-suggestions">
                  {existingCategories.map((cat) => (
                    <option key={cat} value={cat} />
                  ))}
                </datalist>
              </label>

              <label className="field">
                <span>Date</span>
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </label>
            </div>

            <div className="recurring-checkbox-row">
              <label className="recurring-label">
                <input
                  type="checkbox"
                  checked={isRecurring}
                  onChange={(e) => setIsRecurring(e.target.checked)}
                />
                <span className="recurring-text">
                  <strong>Make this expense recurring for each month</strong>
                  <small>Automatically included in the calculations of all future and past months</small>
                </span>
              </label>
            </div>

            {errorMessage && (
              <p className="feedback feedback--error" role="alert">
                {errorMessage}
              </p>
            )}
          </div>

          <footer className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={submitting || !name.trim() || !amount.trim()}>
              {submitting ? 'Adding…' : isRecurring ? '+ Add Recurring Expense' : '+ Add Expense'}
            </button>
          </footer>
        </form>
      </div>
    </div>
  )
}

