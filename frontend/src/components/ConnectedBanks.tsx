import { useEffect, useState } from 'react'
import { getBanks } from '../api/banks'
import type { ConnectedBank } from '../types/banks'

interface ConnectedBanksProps {
  /** Connection stage from usePlaidConnection; the list reloads whenever it reaches 'connected'. */
  stage: string
  busy: boolean
  onAddBank: () => void
}

export function ConnectedBanks({ stage, busy, onAddBank }: ConnectedBanksProps) {
  const [banks, setBanks] = useState<ConnectedBank[]>([])

  useEffect(() => {
    // Load on first render, and again after a bank is added (stage returns to 'connected').
    if (stage !== 'idle' && stage !== 'connected') return
    let ignore = false
    getBanks()
      .then((res) => {
        if (!ignore) setBanks(res.banks)
      })
      .catch(() => {
        // Best effort: the list is informational.
      })
    return () => {
      ignore = true
    }
  }, [stage])

  if (banks.length === 0) return null

  return (
    <div className="banks-list">
      <p className="banks-title">
        Connected banks <span className="banks-count">{banks.length}</span>
      </p>
      <ul className="banks-items">
        {banks.map((bank) => (
          <li key={bank.item_id} className="banks-item">
            <span className="banks-name">{bank.institution_name}</span>
            <span className="banks-meta">
              {bank.transaction_count} transaction{bank.transaction_count === 1 ? '' : 's'}
            </span>
          </li>
        ))}
      </ul>
      <button type="button" className="banks-add" onClick={onAddBank} disabled={busy}>
        + Add another bank
      </button>
    </div>
  )
}
