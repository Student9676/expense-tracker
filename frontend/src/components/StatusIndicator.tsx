import type { ConnectionStage } from '../types/plaid'

const LABELS: Record<ConnectionStage, string> = {
  idle: 'Ready',
  'checking-server': 'Working',
  initializing: 'Working',
  'creating-link-token': 'Working',
  'awaiting-link': 'Waiting',
  'saving-token': 'Working',
  connected: 'Connected',
  error: 'Error',
}

interface StatusIndicatorProps {
  stage: ConnectionStage
}

export function StatusIndicator({ stage }: StatusIndicatorProps) {
  return (
    <span className={`status-dot status-dot--${stage}`} role="status">
      {LABELS[stage]}
    </span>
  )
}
