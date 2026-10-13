import { useEffect, useState } from 'react'
import { AdvancedPanel } from './components/AdvancedPanel'
import { BudgetPage } from './components/BudgetPage'
import { ConnectButton } from './components/ConnectButton'
import { ConnectedBanks } from './components/ConnectedBanks'
import { StatusIndicator } from './components/StatusIndicator'
import { TransactionsPanel } from './components/TransactionsPanel'
import { usePlaidConnection } from './hooks/usePlaidConnection'
import { useTransactions } from './hooks/useTransactions'
import './App.css'

type PageTab = 'budget' | 'connection'

function getInitialPage(): PageTab {
  if (typeof window !== 'undefined' && window.location.hash === '#connection') {
    return 'connection'
  }
  return 'budget'
}

function App() {
  const [activePage, setActivePage] = useState<PageTab>(getInitialPage)

  const {
    stage,
    connectionSource,
    busy,
    linkReady,
    publicToken,
    output,
    errorMessage,
    connect,
    manual,
  } = usePlaidConnection()
  const transactions = useTransactions()

  useEffect(() => {
    const handleHashChange = () => {
      if (window.location.hash === '#connection') {
        setActivePage('connection')
      } else {
        setActivePage('budget')
      }
    }
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  const handlePageSwitch = (page: PageTab) => {
    setActivePage(page)
    window.location.hash = page === 'connection' ? '#connection' : '#budget'
  }

  return (
    <main className="shell">
      <header className="masthead">
        <div>
          <p className="kicker">Expense tracker</p>
          <h1>{activePage === 'budget' ? 'Monthly Budget' : 'Connection desk'}</h1>
        </div>
        <div className="masthead-controls">
          <nav className="nav-tabs" aria-label="Page navigation">
            <button
              type="button"
              className={`nav-tab ${activePage === 'budget' ? 'nav-tab--active' : ''}`}
              onClick={() => handlePageSwitch('budget')}
            >
              Monthly Budget
            </button>
            <button
              type="button"
              className={`nav-tab ${activePage === 'connection' ? 'nav-tab--active' : ''}`}
              onClick={() => handlePageSwitch('connection')}
            >
              Connection Desk
            </button>
          </nav>
          {activePage === 'connection' && <StatusIndicator stage={stage} />}
        </div>
      </header>

      {activePage === 'budget' ? (
        <BudgetPage />
      ) : (
        <>
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
                  {connectionSource === 'saved'
                    ? 'Account already connected. A saved access token is ready to use.'
                    : 'Account connected. The access token was created and saved on the server.'}
                </p>
              )}
              {errorMessage && (
                <p className="feedback feedback--error" role="alert">
                  {errorMessage}
                </p>
              )}

              <ConnectedBanks stage={stage} busy={busy} onAddBank={connect} />
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

          <TransactionsPanel
            startDate={transactions.startDate}
            endDate={transactions.endDate}
            status={transactions.status}
            action={transactions.action}
            loading={transactions.loading}
            output={transactions.output}
            count={transactions.count}
            saveResult={transactions.saveResult}
            onStartDateChange={transactions.setStartDate}
            onEndDateChange={transactions.setEndDate}
            onFetch={transactions.fetchTransactions}
            onSave={transactions.saveToDatabase}
          />
        </>
      )}
    </main>
  )
}

export default App

