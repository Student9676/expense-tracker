import type { ApiResponse } from '../types/plaid'
import { request } from './client'

export function checkServer(): Promise<ApiResponse> {
  return request('/')
}

export function initializePlaid(): Promise<ApiResponse> {
  return request('/api/initialize', { method: 'POST' })
}

export async function createLinkToken(): Promise<{ linkToken: string; response: ApiResponse }> {
  const response = await request('/api/create_link_token', { method: 'POST' })
  const linkToken = response.link_token

  if (typeof linkToken !== 'string') {
    throw new Error('Server response did not include a Link token')
  }

  return { linkToken, response }
}

export function exchangePublicToken(publicToken: string): Promise<ApiResponse> {
  return request('/api/set_access_token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ public_token: publicToken }),
  })
}
