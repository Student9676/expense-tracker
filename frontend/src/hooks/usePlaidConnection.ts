import { useCallback, useEffect, useRef, useState } from 'react'
import { usePlaidLink } from 'react-plaid-link'
import * as plaidApi from '../api/plaid'
import type { ApiResponse, ConnectionStage } from '../types/plaid'

const LINK_TOKEN_STORAGE_KEY = 'plaid_link_token'
const BUSY_STAGES: ConnectionStage[] = [
  'checking-server',
  'initializing',
  'creating-link-token',
  'saving-token',
]

function getOAuthRedirectUri(): string | undefined {
  return window.location.search.includes('oauth_state_id') ? window.location.href : undefined
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Request failed'
}

export function usePlaidConnection() {
  const [linkToken, setLinkToken] = useState(
    () => sessionStorage.getItem(LINK_TOKEN_STORAGE_KEY) ?? '',
  )
  const [receivedRedirectUri] = useState(getOAuthRedirectUri)
  const [publicToken, setPublicToken] = useState('')
  const [output, setOutput] = useState<ApiResponse>({ status: 'ready' })
  const [stage, setStage] = useState<ConnectionStage>('idle')

  // Set when Plaid Link should open as soon as it is ready: after a fresh Link
  // token is created, or when returning from an OAuth redirect.
  const pendingOpenRef = useRef(Boolean(receivedRedirectUri && linkToken))

  const handleError = useCallback((error: unknown) => {
    setOutput({ error: toErrorMessage(error) })
    setStage('error')
  }, [])

  const { open, ready } = usePlaidLink({
    token: linkToken,
    receivedRedirectUri,
    onSuccess: async (token) => {
      if (!token) {
        handleError(new Error('Plaid Link completed without a public token'))
        return
      }

      setPublicToken(token)
      sessionStorage.removeItem(LINK_TOKEN_STORAGE_KEY)
      setStage('saving-token')

      try {
        setOutput(await plaidApi.exchangePublicToken(token))
        setStage('connected')
      } catch (error) {
        handleError(error)
      }
    },
    onExit: (error, metadata) => {
      setOutput({
        status: 'link exited',
        error: error?.display_message ?? error?.error_message ?? null,
        metadata,
      })
      setStage(error ? 'error' : 'idle')
    },
  })

  useEffect(() => {
    if (pendingOpenRef.current && ready) {
      pendingOpenRef.current = false
      open()
    }
  }, [open, ready])

  const runCheckServer = useCallback(async () => {
    setStage('checking-server')
    setOutput(await plaidApi.checkServer())
  }, [])

  const runInitialize = useCallback(async () => {
    setStage('initializing')
    setOutput(await plaidApi.initializePlaid())
  }, [])

  const runCreateLinkToken = useCallback(async () => {
    setStage('creating-link-token')
    const { linkToken: token, response } = await plaidApi.createLinkToken()
    sessionStorage.setItem(LINK_TOKEN_STORAGE_KEY, token)
    setLinkToken(token)
    setOutput(response)
  }, [])

  /** The whole flow: check server, initialize Plaid, create a Link token, open Link. */
  const connect = useCallback(async () => {
    try {
      await runCheckServer()
      await runInitialize()
      await runCreateLinkToken()
      pendingOpenRef.current = true
      setStage('awaiting-link')
    } catch (error) {
      handleError(error)
    }
  }, [handleError, runCheckServer, runInitialize, runCreateLinkToken])

  /** Wraps a single manual step so it reports errors and returns to idle. */
  const runManualStep = useCallback(
    (step: () => Promise<void>) => async () => {
      try {
        await step()
        setStage('idle')
      } catch (error) {
        handleError(error)
      }
    },
    [handleError],
  )

  const openLink = useCallback(() => open(), [open])

  const errorMessage =
    stage === 'error' && typeof output.error === 'string' ? output.error : null

  return {
    stage,
    busy: BUSY_STAGES.includes(stage),
    linkReady: ready,
    publicToken,
    output,
    errorMessage,
    connect,
    manual: {
      checkServer: runManualStep(runCheckServer),
      initialize: runManualStep(runInitialize),
      createLinkToken: runManualStep(runCreateLinkToken),
      openLink,
    },
  }
}
