export interface BankAccount {
  account_id: string
  name: string | null
  mask: string | null
  /** Plaid account type: depository, credit, loan, investment. */
  type: string
  subtype: string
  transaction_count: number
  /** False when the server is set to import only certain account types (PLAID_ACCOUNT_TYPES). */
  tracked: boolean
}

export interface ConnectedBank {
  item_id: string
  institution_id: string | null
  institution_name: string
  created_at: string
  transaction_count: number
  accounts: BankAccount[]
  accounts_error: string | null
}

export interface BanksResponse {
  banks: ConnectedBank[]
}

export interface RemoveBankResult {
  status: string
  item_id: string
  institution_name: string
  plaid_removed: boolean
  keychain_removed: boolean
  transactions_deleted: number
  bank_count: number
  warnings: string[]
}
