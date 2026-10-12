import { LuChevronLeft, LuChevronRight } from 'react-icons/lu'
import { formatMonthLabel } from '../utils/format'

interface MonthStepperProps {
  /** Months with data, newest first. */
  months: string[]
  value: string
  onChange: (month: string) => void
}

export function MonthStepper({ months, value, onChange }: MonthStepperProps) {
  const isAll = value.toLowerCase() === 'all'
  const index = months.indexOf(value)
  // months is newest-first, so the "previous" month is the next index.
  const previous = !isAll && index >= 0 ? months[index + 1] : undefined
  const next = !isAll && index > 0 ? months[index - 1] : undefined

  return (
    <div className="month-stepper" role="group" aria-label="Select month">
      <button
        type="button"
        className="month-stepper-btn"
        onClick={() => previous && onChange(previous)}
        disabled={!previous}
        aria-label="Previous month"
        title={previous ? formatMonthLabel(previous) : 'No earlier month'}
      >
        <LuChevronLeft size={16} aria-hidden="true" />
      </button>

      <select
        className="month-stepper-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Month"
      >
        {months.map((m) => (
          <option key={m} value={m}>
            {formatMonthLabel(m)}
          </option>
        ))}
        <option value="all">All Months (Overall)</option>
      </select>

      <button
        type="button"
        className="month-stepper-btn"
        onClick={() => next && onChange(next)}
        disabled={!next}
        aria-label="Next month"
        title={next ? formatMonthLabel(next) : 'No later month'}
      >
        <LuChevronRight size={16} aria-hidden="true" />
      </button>
    </div>
  )
}
