import type { CategorySummaryResponse } from '../types/budget'
import { formatCurrency } from '../utils/format'

interface CategoryTotalsTableProps {
  summary: CategorySummaryResponse | null
  loading: boolean
  error: string | null
}

export function CategoryTotalsTable({ summary, loading, error }: CategoryTotalsTableProps) {
  const rows = summary?.categories ?? []

  return (
    <>
      {error && (
        <p className="feedback feedback--error" role="alert">
          {error}
        </p>
      )}
      {!error && !summary && loading && <p className="loading-state">Loading category totals…</p>}

      {!error && summary && (
        <div className={loading ? 'table-responsive table-stale' : 'table-responsive'}>
          <table className="expenses-table category-totals-table">
            <thead>
              <tr>
                <th className="col-category-name">Category</th>
                <th className="col-count">Transactions</th>
                <th className="col-amount">Total</th>
                <th className="col-share">Share</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.category}>
                  <td className="col-category-name">
                    <span
                      className={`category-tag category-tag--${row.category
                        .toLowerCase()
                        .replace(/[^a-z0-9]/g, '-')}`}
                    >
                      {row.category}
                    </span>
                  </td>
                  <td className="col-count">{row.count}</td>
                  <td className="col-amount">
                    <span className={`amount-text ${row.total < 0 ? 'amount-text--credit' : ''}`}>
                      {formatCurrency(row.total)}
                    </span>
                  </td>
                  <td className="col-share">{row.share.toFixed(1)}%</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="empty-table-cell">
                    No included transactions for the current filters.
                  </td>
                </tr>
              )}
            </tbody>
            {rows.length > 0 && (
              <tfoot>
                <tr className="tfoot-row tfoot-row--expenses">
                  <td className="tfoot-label tfoot-label--left">
                    Total{summary.excluded_count > 0 ? ` (excl. ${summary.excluded_count} excluded)` : ''}
                  </td>
                  <td className="col-count tfoot-value">{summary.count}</td>
                  <td className="tfoot-value">{formatCurrency(summary.total)}</td>
                  <td className="tfoot-value">100%</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </>
  )
}
