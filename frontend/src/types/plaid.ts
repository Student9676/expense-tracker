export type ApiResponse = Record<string, unknown>

export interface ConnectionStatus {
  connected: boolean
}

/** Whether the connected account came from a token already saved or a Link just completed. */
export type ConnectionSource = 'saved' | 'new'

export type Transaction = Record<string, unknown>

export type TransactionsResponse = Transaction[]

export type TransactionsStatus = 'idle' | 'loading' | 'success' | 'error'

export type ConnectionStage =
  | 'idle'
  | 'checking-server'
  | 'initializing'
  | 'creating-link-token'
  | 'awaiting-link'
  | 'saving-token'
  | 'connected'
  | 'error'
