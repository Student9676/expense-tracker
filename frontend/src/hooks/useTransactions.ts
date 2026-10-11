import { useCallback, useState } from 'react'
import { getTransactions, saveTransactions } from '../api/plaid'
import type {
  ApiResponse,
  SaveTransactionsResult,
  TransactionsAction,
  TransactionsResponse,
  TransactionsStatus,
} from '../types/plaid'

const DEFAULT_RANGE_DAYS = 30

/** Formats a date as YYYY-MM-DD in the user's local time zone (not UTC). */
function formatLocalDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function getDefaultStartDate(): string {
  const date = new Date()
  date.setDate(date.getDate() - DEFAULT_RANGE_DAYS)
  return formatLocalDate(date)
}

function getDefaultEndDate(): string {
  return formatLocalDate(new Date())
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Request failed'
}

export function useTransactions() {
  const [startDate, setStartDate] = useState(getDefaultStartDate)
  const [endDate, setEndDate] = useState(getDefaultEndDate)
  const [status, setStatus] = useState<TransactionsStatus>('idle')
  const [action, setAction] = useState<TransactionsAction | null>(null)
  const [output, setOutput] = useState<
    TransactionsResponse | SaveTransactionsResult | ApiResponse | null
  >(null)
  const [saveResult, setSaveResult] = useState<SaveTransactionsResult | null>(null)

  /** Validates the date range and marks the request as started. Returns false if it was rejected. */
  const begin = useCallback(
    (nextAction: TransactionsAction): boolean => {
      setAction(nextAction)
      setSaveResult(null)

      // YYYY-MM-DD strings compare correctly as plain strings.
      if (startDate > endDate) {
        setOutput({ error: 'Start date must be on or before end date' })
        setStatus('error')
        return false
      }

      setStatus('loading')
      return true
    },
    [startDate, endDate],
  )

  const fail = useCallback((error: unknown) => {
    setOutput({ error: toErrorMessage(error) })
    setStatus('error')
  }, [])

  const fetchTransactions = useCallback(async () => {
    if (!begin('fetch')) return

    try {
      setOutput(await getTransactions(startDate, endDate))
      setStatus('success')
    } catch (error) {
      fail(error)
    }
  }, [begin, fail, startDate, endDate])

  const saveToDatabase = useCallback(async () => {
    if (!begin('save')) return

    try {
      const result = await saveTransactions(startDate, endDate)
      setOutput(result)
      setSaveResult(result)
      setStatus('success')
    } catch (error) {
      fail(error)
    }
  }, [begin, fail, startDate, endDate])

  const count =
    action === 'fetch' && status === 'success' && Array.isArray(output) ? output.length : null

  return {
    startDate,
    endDate,
    setStartDate,
    setEndDate,
    status,
    action,
    loading: status === 'loading',
    output,
    count,
    saveResult,
    fetchTransactions,
    saveToDatabase,
  }
}
