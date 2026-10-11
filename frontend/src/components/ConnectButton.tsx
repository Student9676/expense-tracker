import type { ConnectionStage } from '../types/plaid'

const LABELS: Record<ConnectionStage, string> = {
  idle: 'Connect account',
  'checking-server': 'Checking server…',
  initializing: 'Initializing Plaid…',
  'creating-link-token': 'Creating Link token…',
  'awaiting-link': 'Waiting for Plaid Link…',
  'saving-token': 'Saving access token…',
  connected: 'Reconnect account',
  error: 'Try again',
}

interface ConnectButtonProps {
  stage: ConnectionStage
  busy: boolean
  onClick: () => void
}

export function ConnectButton({ stage, busy, onClick }: ConnectButtonProps) {
  return (
    <button type="button" className="connect-button" onClick={onClick} disabled={busy}>
      {LABELS[stage]}
    </button>
  )
}
