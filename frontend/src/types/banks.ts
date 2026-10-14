export interface ConnectedBank {
  item_id: string
  institution_id: string | null
  institution_name: string
  created_at: string
  transaction_count: number
}

export interface BanksResponse {
  banks: ConnectedBank[]
}
