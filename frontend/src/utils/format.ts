export function formatCurrency(val: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val)
}

export function formatMonthLabel(m: string): string {
  if (!m || m.toLowerCase() === 'all') return 'All Months'
  const parts = m.split('-')
  if (parts.length === 2) {
    const year = Number(parts[0])
    const monthIndex = Number(parts[1]) - 1
    const date = new Date(year, monthIndex, 1)
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
    }
  }
  return m
}
