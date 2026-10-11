import type {
  ApiResponse,
  SaveTransactionsResult,
  TransactionsAction,
  TransactionsResponse,
  TransactionsStatus,
} from '../types/plaid'

interface TransactionsPanelProps {
  startDate: string
  endDate: string
  status: TransactionsStatus
  action: TransactionsAction | null
  loading: boolean
  output: TransactionsResponse | SaveTransactionsResult | ApiResponse | null
  count: number | null
  saveResult: SaveTransactionsResult | null
  onStartDateChange: (value: string) => void
  onEndDateChange: (value: string) => void
  onFetch: () => void
  onSave: () => void
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}

function describeSave(result: SaveTransactionsResult): string {
  const saved = result.inserted + result.updated
  const parts = [
    `Saved ${plural(saved, 'transaction')} (${result.inserted} new, ${result.updated} updated).`,
    `${plural(result.total_in_database, 'transaction')} in the database.`,
  ]

  if (result.pending_removed > 0) {
    parts.push(
      `${plural(result.pending_removed, 'pending transaction')} removed (posted or cancelled).`,
    )
  }
  if (result.skipped > 0) {
    parts.push(`${result.skipped} skipped (no transaction ID).`)
  }

  return parts.join(' ')
}

export function TransactionsPanel({
  startDate,
  endDate,
  status,
  action,
  loading,
  output,
  count,
  saveResult,
  onStartDateChange,
  onEndDateChange,
  onFetch,
  onSave,
}: TransactionsPanelProps) {
  const canRun = !loading && startDate !== '' && endDate !== ''

  return (
    <section className="workspace transactions" aria-label="Transactions">
      <div className="panel-body">
        <div className="section-heading">
          <h3>Transactions</h3>
        </div>

        <div className="transactions-controls">
          <label className="field">
            <span>Start date</span>
            <input
              type="date"
              value={startDate}
              onChange={(event) => onStartDateChange(event.target.value)}
            />
          </label>
          <label className="field">
            <span>End date</span>
            <input
              type="date"
              value={endDate}
              onChange={(event) => onEndDateChange(event.target.value)}
            />
          </label>
          <div className="transactions-actions">
            <button type="button" onClick={onFetch} disabled={!canRun}>
              {loading && action === 'fetch' ? 'Fetching…' : 'Get transactions'}
            </button>
            <button type="button" onClick={onSave} disabled={!canRun}>
              {loading && action === 'save' ? 'Saving…' : 'Save to database'}
            </button>
          </div>
        </div>

        {count !== null && (
          <p className="feedback feedback--success" role="status">
            Fetched {plural(count, 'transaction')}.
          </p>
        )}
        {saveResult !== null && (
          <p className="feedback feedback--success" role="status">
            {describeSave(saveResult)}
          </p>
        )}
        {status === 'error' && (
          <p className="feedback feedback--error" role="alert">
            The request failed. Details are in the response box below.
          </p>
        )}

        <textarea
          className="transactions-output"
          aria-label="Transactions response"
          readOnly
          value={output === null ? '' : JSON.stringify(output, null, 2)}
          placeholder="The server response appears here"
        />
      </div>
    </section>
  )
}
