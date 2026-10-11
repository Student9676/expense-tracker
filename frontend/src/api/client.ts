import type { ApiResponse } from '../types/plaid'

const API_BASE = '/backend'

export async function request(path: string, options?: RequestInit): Promise<ApiResponse> {
  const response = await fetch(`${API_BASE}${path}`, options)
  const rawBody = await response.text()
  let body: ApiResponse = {}

  try {
    body = JSON.parse(rawBody) as ApiResponse
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
