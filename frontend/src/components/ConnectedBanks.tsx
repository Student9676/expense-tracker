import { useEffect, useState } from 'react'
import { getBanks, removeBank } from '../api/banks'
import type { ConnectedBank } from '../types/banks'

interface ConnectedBanksProps {
  /** Connection stage from usePlaidConnection; the list reloads whenever it reaches 'connected'. */
  stage: string
  busy: boolean
  onAddBank: () => void
  /** Called after a bank is removed so the page can re-check the connection status. */
  onBanksChanged: () => Promise<void> | void
}

interface Notice {
  kind: 'success' | 'error'
  text: string
}

function accountLabel(name: string | null, mask: string | null): string {
  const base = name ?? 'Account'
  return mask ? `${base} ••${mask}` : base
}

export function ConnectedBanks({ stage, busy, onAddBank, onBanksChanged }: ConnectedBanksProps) {
  const [banks, setBanks] = useState<ConnectedBank[]>([])
  const [reloadKey, setReloadKey] = useState(0)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [deleteTransactions, setDeleteTransactions] = useState(false)
  const [removingId, setRemovingId] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)

  useEffect(() => {
    // Load on first render, and again after a bank is added or removed.
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
  }, [stage, reloadKey])

  const startConfirm = (bank: ConnectedBank) => {
    setConfirmId(bank.item_id)
    setDeleteTransactions(false)
    setNotice(null)
  }

  const handleRemove = async (bank: ConnectedBank) => {
    setRemovingId(bank.item_id)
    setNotice(null)
    try {
      const result = await removeBank(bank.item_id, deleteTransactions)
      setConfirmId(null)
      setDeleteTransactions(false)
      const deleted =
        result.transactions_deleted > 0
          ? ` and ${result.transactions_deleted} saved transactions were deleted`
          : ''
      setNotice(
        result.warnings.length > 0
          ? { kind: 'error', text: result.warnings.join(' ') }
          : { kind: 'success', text: `${result.institution_name} was disconnected${deleted}.` },
      )
      setReloadKey((key) => key + 1)
      await onBanksChanged()
    } catch (err) {
      setNotice({
        kind: 'error',
        text: err instanceof Error ? err.message : 'Failed to remove the bank.',
      })
    } finally {
      setRemovingId(null)
    }
  }

  if (banks.length === 0 && !notice) return null

  return (
    <div className="banks-list">
      {banks.length > 0 && (
        <p className="banks-title">
          Connected banks <span className="banks-count">{banks.length}</span>
        </p>
      )}

      {notice && (
        <p
          className={`feedback ${notice.kind === 'success' ? 'feedback--success' : 'feedback--error'}`}
          role={notice.kind === 'success' ? 'status' : 'alert'}
        >
          {notice.text}
        </p>
      )}

      <ul className="banks-items">
        {banks.map((bank) => {
          const confirming = confirmId === bank.item_id
          const removing = removingId === bank.item_id
          return (
            <li key={bank.item_id} className="banks-item">
              <div className="banks-item-head">
                <span className="banks-name">{bank.institution_name}</span>
                {!confirming && (
                  <button
                    type="button"
                    className="banks-remove"
                    onClick={() => startConfirm(bank)}
                    disabled={removingId !== null || busy}
                  >
                    Remove
                  </button>
                )}
              </div>

              {bank.accounts_error ? (
                <p className="banks-account-error">{bank.accounts_error}</p>
              ) : (
                <ul className="banks-accounts">
                  {bank.accounts.map((account) => (
                    <li key={account.account_id} className="banks-account">
                      <span className="banks-account-name">
                        {accountLabel(account.name, account.mask)}
                      </span>
                      <span className="banks-account-type">
                        {[account.type, account.subtype].filter(Boolean).join(' · ')}
                      </span>
                      <span className="banks-account-count">
                        {account.tracked
                          ? `${account.transaction_count} transaction${account.transaction_count === 1 ? '' : 's'}`
                          : 'not imported'}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {confirming && (
                <div className="banks-confirm" role="alertdialog" aria-label={`Remove ${bank.institution_name}`}>
                  <p>
                    Disconnect <strong>{bank.institution_name}</strong>? This removes the connection at
                    Plaid and deletes its access token from your Keychain.
                  </p>
                  <label className="banks-confirm-option">
                    <input
                      type="checkbox"
                      checked={deleteTransactions}
                      onChange={(e) => setDeleteTransactions(e.target.checked)}
                      disabled={removing}
                    />
                    Also delete its {bank.transaction_count} saved transaction
                    {bank.transaction_count === 1 ? '' : 's'}
                  </label>
                  <div className="banks-confirm-actions">
                    <button
                      type="button"
                      className="banks-confirm-delete"
                      onClick={() => void handleRemove(bank)}
                      disabled={removing}
                    >
                      {removing ? 'Removing…' : 'Yes, disconnect'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmId(null)}
                      disabled={removing}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </li>
          )
        })}
      </ul>

      {banks.length > 0 && (
        <button
          type="button"
          className="banks-add"
          onClick={onAddBank}
          disabled={busy || removingId !== null}
        >
          + Add another bank
        </button>
      )}
    </div>
  )
}
