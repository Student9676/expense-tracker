import type { BanksResponse, RemoveBankResult } from '../types/banks'
import { request } from './client'

export function getBanks(): Promise<BanksResponse> {
  return request<BanksResponse>('/api/banks')
}

/** Disconnect a bank: removes it at Plaid, deletes its Keychain token and forgets it. */
export function removeBank(itemId: string, deleteTransactions: boolean): Promise<RemoveBankResult> {
  const query = `?delete_transactions=${deleteTransactions ? 'true' : 'false'}`
  return request<RemoveBankResult>(`/api/banks/${encodeURIComponent(itemId)}${query}`, {
    method: 'DELETE',
  })
}
