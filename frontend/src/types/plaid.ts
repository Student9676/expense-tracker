export type ApiResponse = Record<string, unknown>

export interface ConnectionStatus {
  connected: boolean
}

/** Whether the connected account came from a token already saved or a Link just completed. */
export type ConnectionSource = 'saved' | 'new'

export type Transaction = Record<string, unknown>

export type TransactionsResponse = Transaction[]

export type TransactionsStatus = 'idle' | 'loading' | 'success' | 'error'

/** Which transactions button was used last. */
export type TransactionsAction = 'fetch' | 'save'

/** What the server reports after saving transactions to the database. */
export interface SaveTransactionsResult {
  fetched: number
  inserted: number
  updated: number
  skipped: number
  pending_removed: number
  total_in_database: number
}

export type ConnectionStage =
  | 'idle'
  | 'checking-server'
  | 'initializing'
  | 'creating-link-token'
  | 'awaiting-link'
  | 'saving-token'
  | 'connected'
  | 'error'
