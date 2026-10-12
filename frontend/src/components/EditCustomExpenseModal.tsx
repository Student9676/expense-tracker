import { useEffect, useState } from 'react'
import type { CustomExpenseInput, ExpenseItem } from '../types/budget'
import { updateCustomExpense } from '../api/budget'

interface EditCustomExpenseModalProps {
  isOpen: boolean
  item: ExpenseItem | null
  existingCategories: string[]
  onClose: () => void
  onSaved: (updated: ExpenseItem) => void
}

export function EditCustomExpenseModal({
  isOpen,
  item,
  existingCategories,
  onClose,
  onSaved,
}: EditCustomExpenseModalProps) {
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('')
  const [date, setDate] = useState('')
  const [isRecurring, setIsRecurring] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // Populate fields whenever the item changes (or modal opens)
  useEffect(() => {
    if (item) {
      setName(item.name)
      setAmount(item.amount.toFixed(2))
      setCategory(item.category ?? '')
      setDate(item.date ?? '')
      setIsRecurring(item.is_recurring ?? false)
      setErrorMessage(null)
    }
  }, [item])

  if (!isOpen || !item) return null

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

    const payload: Partial<CustomExpenseInput> = {
      name: name.trim(),
      amount: numAmount,
      category: category.trim() || undefined,
      date: date || undefined,
      is_recurring: isRecurring,
    }

    const customId = item.custom_id ?? item.transaction_id

    try {
      const updated = await updateCustomExpense(customId, payload)
      onSaved(updated)
      onClose()
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to update custom expense')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="edit-custom-modal-title">
      <div className="modal-window modal-window--compact">
        <header className="modal-header">
          <div>
            <p className="kicker">Custom expense</p>
            <h2 id="edit-custom-modal-title" className="modal-title">Edit Custom Expense</h2>
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
              Edit this custom expense. Changes will be saved immediately.
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
                  list="edit-category-suggestions"
                  placeholder="e.g. Housing or leave blank for auto-rules"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                />
                <datalist id="edit-category-suggestions">
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
              {submitting ? 'Saving…' : 'Save Changes'}
            </button>
          </footer>
        </form>
      </div>
    </div>
  )
}

