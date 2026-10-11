export type ApiResponse = Record<string, unknown>

export type ConnectionStage =
  | 'idle'
  | 'checking-server'
  | 'initializing'
  | 'creating-link-token'
  | 'awaiting-link'
  | 'saving-token'
  | 'connected'
  | 'error'
