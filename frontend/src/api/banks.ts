import type { BanksResponse } from '../types/banks'
import { request } from './client'

export function getBanks(): Promise<BanksResponse> {
  return request<BanksResponse>('/api/banks')
}
