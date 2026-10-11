import { AdvancedPanel } from './components/AdvancedPanel'
import { ConnectButton } from './components/ConnectButton'
import { StatusIndicator } from './components/StatusIndicator'
import { usePlaidConnection } from './hooks/usePlaidConnection'
import './App.css'

function App() {
  const { stage, busy, linkReady, publicToken, output, errorMessage, connect, manual } =
    usePlaidConnection()

  return (
    <main className="shell">
      <header className="masthead">
        <div>
          <p className="kicker">Expense tracker</p>
          <h1>Connection desk</h1>
        </div>
        <StatusIndicator stage={stage} />
      </header>

      <section className="intro">
        <p className="eyebrow">Plaid setup</p>
        <h2>Connect your financial world.</h2>
        <p className="lede">
          One click runs the full setup: server check, Plaid initialization, Link, and access
          token creation. Sensitive credentials stay on the server.
        </p>
      </section>

      <section className="workspace" aria-label="Plaid connection">
        <div className="connect-panel">
          <ConnectButton stage={stage} busy={busy} onClick={connect} />

          {stage === 'connected' && (
            <p className="feedback feedback--success" role="status">
              Account connected. The access token was created and saved on the server.
            </p>
          )}
          {errorMessage && (
            <p className="feedback feedback--error" role="alert">
              {errorMessage}
            </p>
          )}
        </div>

        <AdvancedPanel
          busy={busy}
          linkReady={linkReady}
          publicToken={publicToken}
          output={output}
          onCheckServer={manual.checkServer}
          onInitialize={manual.initialize}
          onCreateLinkToken={manual.createLinkToken}
          onOpenLink={manual.openLink}
        />
      </section>
    </main>
  )
}

export default App
