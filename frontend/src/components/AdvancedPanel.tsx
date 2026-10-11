import type { ApiResponse } from '../types/plaid'

interface AdvancedPanelProps {
  busy: boolean
  linkReady: boolean
  publicToken: string
  output: ApiResponse
  onCheckServer: () => void
  onInitialize: () => void
  onCreateLinkToken: () => void
  onOpenLink: () => void
}

export function AdvancedPanel({
  busy,
  linkReady,
  publicToken,
  output,
  onCheckServer,
  onInitialize,
  onCreateLinkToken,
  onOpenLink,
}: AdvancedPanelProps) {
  return (
    <details className="advanced">
      <summary>Advanced</summary>

      <div className="advanced-body">
        <section aria-labelledby="manual-steps-heading">
          <div className="section-heading">
            <span className="section-number">01</span>
            <h3 id="manual-steps-heading">Run steps manually</h3>
          </div>
          <div className="button-grid">
            <button type="button" onClick={onCheckServer} disabled={busy}>
              Check server
            </button>
            <button type="button" onClick={onInitialize} disabled={busy}>
              Initialize Plaid
            </button>
            <button type="button" onClick={onCreateLinkToken} disabled={busy}>
              Create Link token
            </button>
            <button type="button" onClick={onOpenLink} disabled={busy || !linkReady}>
              Open Plaid Link
            </button>
          </div>
        </section>

        <section aria-labelledby="public-token-heading">
          <div className="section-heading">
            <span className="section-number">02</span>
            <h3 id="public-token-heading">Public token</h3>
          </div>
          <p className="token-note">
            Plaid Link returns the public token automatically after a successful connection.
          </p>
          <input
            aria-label="Public token"
            type="password"
            value={publicToken}
            readOnly
            placeholder="Public token appears after Link"
            autoComplete="off"
          />
        </section>

        <section aria-labelledby="output-heading">
          <div className="section-heading">
            <span className="section-number">03</span>
            <h3 id="output-heading">Output</h3>
          </div>
          <textarea
            aria-label="Action output"
            readOnly
            value={JSON.stringify(output, null, 2)}
          />
        </section>
      </div>
    </details>
  )
}
