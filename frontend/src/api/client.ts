import type { ApiResponse } from '../types/plaid'

const API_BASE = '/backend'

function isRecord(value: unknown): value is ApiResponse {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export async function request<T = ApiResponse>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options)
  const rawBody = await response.text()
  let body: unknown = {}

  try {
    body = JSON.parse(rawBody)
  } catch {
    body = {}
  }

  if (!response.ok) {
    const detail = isRecord(body) ? (body.detail ?? body.error) : undefined
    const message = typeof detail === 'string' ? detail : rawBody.slice(0, 300)
    throw new Error(message || `Request failed with status ${response.status}`)
  }

  return body as T
}
