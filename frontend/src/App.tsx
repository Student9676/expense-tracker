import { useEffect, useState } from 'react'
import { usePlaidLink } from 'react-plaid-link'
import './App.css'

type Output = Record<string, unknown>

async function request(path: string, options?: RequestInit): Promise<Output> {
  const response = await fetch(`/backend${path}`, options)
  const rawBody = await response.text()
  let body: Output = {}

  try {
    body = JSON.parse(rawBody) as Output
  } catch {
    body = {}
  }

  if (!response.ok) {
    const detail = body.detail ?? body.error
    const message = typeof detail === 'string' ? detail : rawBody.slice(0, 300)
    throw new Error(message || `Request failed with status ${response.status}`)
  }

  return body
}

function App() {
  const [linkToken, setLinkToken] = useState(
    () => sessionStorage.getItem('plaid_link_token') ?? '',
  )
  const [publicToken, setPublicToken] = useState('')
  const [output, setOutput] = useState<Output>({ status: 'ready' })
  const [busy, setBusy] = useState(false)
  const callbackUrl = window.location.search.includes('oauth_state_id')
    ? window.location.href
    : undefined

  async function run(action: () => Promise<Output>) {
    setBusy(true)
    try {
      setOutput(await action())
    } catch (error) {
      setOutput({ error: error instanceof Error ? error.message : 'Request failed' })
    } finally {
      setBusy(false)
    }
  }

  const { open, ready } = usePlaidLink({
    token: linkToken,
    receivedRedirectUri: callbackUrl,
    onSuccess: (token) => {
      if (!token) {
        setOutput({ error: 'Plaid Link completed without a public token' })
        return
      }
      setPublicToken(token)
      sessionStorage.removeItem('plaid_link_token')
      void run(() =>
        request('/api/set_access_token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ public_token: token }),
        }),
      )
    },
    onExit: (error, metadata) => {
      setOutput({
        status: 'link exited',
        error: error?.display_message ?? error?.error_message ?? null,
        metadata,
      })
    },
  })

  useEffect(() => {
    if (callbackUrl && linkToken && ready) {
      open()
    }
  }, [callbackUrl, linkToken, open, ready])

  async function createLinkToken() {
    await run(async () => {
      const response = await request('/api/create_link_token', { method: 'POST' })
      const token = response.link_token
      if (typeof token !== 'string') {
        throw new Error('Server response did not include a Link token')
      }
      sessionStorage.setItem('plaid_link_token', token)
      setLinkToken(token)
      return response
    })
  }

  return (
    <main className="shell">
      <header className="masthead">
        <div>
          <p className="kicker">Expense tracker</p>
          <h1>Connection desk</h1>
        </div>
        <span className={`status-dot ${busy ? 'working' : ''}`}>
          {busy ? 'Working' : 'Ready'}
        </span>
      </header>

      <section className="intro">
        <p className="eyebrow">Plaid setup</p>
        <h2>Connect your financial world.</h2>
        <p className="lede">
          Run the server setup steps here. Sensitive credentials stay on the server.
        </p>
      </section>

      <section className="workspace" aria-label="Plaid setup controls">
        <div className="actions">
          <div className="section-heading">
            <span className="section-number">01</span>
            <h3>Server actions</h3>
          </div>
          <div className="button-grid">
            <button type="button" onClick={() => run(() => request('/'))} disabled={busy}>
              Check server
            </button>
            <button
              type="button"
              onClick={() => run(() => request('/api/initialize', { method: 'POST' }))}
              disabled={busy}
            >
              Initialize Plaid
            </button>
            <button type="button" onClick={createLinkToken} disabled={busy}>
              Create Link token
            </button>
            <button
              type="button"
              onClick={() => open()}
              disabled={busy || !ready}
            >
              Open Plaid Link
            </button>
          </div>
        </div>

        <div className="token-panel">
          <div className="section-heading">
            <span className="section-number">02</span>
            <h3>Connection status</h3>
          </div>
          <p className="token-note">
            Plaid Link returns the public token automatically after a successful connection.
          </p>
          <input
            aria-label="Public token"
            type="password"
            value={publicToken}
            onChange={(event) => setPublicToken(event.target.value)}
            placeholder="Public token appears after Link"
            autoComplete="off"
          />
        </div>

        <div className="output-panel">
          <div className="section-heading">
            <span className="section-number">03</span>
            <h3>Output</h3>
          </div>
          <textarea
            aria-label="Action output"
            readOnly
            value={JSON.stringify(output, null, 2)}
          />
        </div>
      </section>
    </main>
  )
}

export default App
