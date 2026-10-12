import { useEffect, useState } from 'react'
import { Cell, Pie, PieChart, Tooltip } from 'recharts'
import type { CategorySummaryResponse } from '../types/budget'
import { formatCurrency } from '../utils/format'
import { LABEL_FONT_SIZE, fitPie, labelTextToFit, measureLabelWidth } from '../utils/pieLabels'
import type { SmallLabelInput } from '../utils/pieLabels'

const SLICE_COLORS = [
  '#007f73',
  '#e07a2f',
  '#3b6ea5',
  '#b5485d',
  '#7a9e3d',
  '#8a5fb0',
  '#c9a227',
  '#2f9fb3',
]
const OTHER_COLOR = '#9aa5a1'

/** Slices below this percent get a leader line + label outside the pie. */
const SMALL_SLICE_PERCENT = 3.5

const LEGEND_WIDTH = 300
/** Space between the pie (or its labels) and the legend when side by side. */
const PIE_LEGEND_GAP = 100
/** Below this width for the pie area, the legend moves under the pie. */
const MIN_PIE_AREA_WIDTH = 360
const STACKED_GAP = 24
const MAX_RADIUS = 230
const MIN_RADIUS = 80
const CANVAS_PADDING = 8
const INNER_RATIO = 0.58

interface CategoryPieChartProps {
  summary: CategorySummaryResponse | null
  loading: boolean
  error: string | null
}

function useElementWidth() {
  const [element, setElement] = useState<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) setWidth(Math.floor(entry.contentRect.width))
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [element])

  return [setElement, width] as const
}

export function CategoryPieChart({ summary, loading, error }: CategoryPieChartProps) {
  const [containerRef, containerWidth] = useElementWidth()

  const slices = summary?.pie ?? []
  const data = slices.map((s, i) => ({
    name: s.is_other ? `Other (${s.merged_categories} categories)` : s.category,
    value: s.total,
    share: s.share,
    count: s.count,
    color: s.is_other ? OTHER_COLOR : SLICE_COLORS[i % SLICE_COLORS.length],
  }))

  // --- Layout: size the pie so it, its labels and the legend fit and sit centred together ---
  const sideBySide =
    containerWidth === 0 || containerWidth >= LEGEND_WIDTH + PIE_LEGEND_GAP + MIN_PIE_AREA_WIDTH
  const pieAreaWidth = (containerWidth || 1000) - (sideBySide ? LEGEND_WIDTH + PIE_LEGEND_GAP : 0)

  // Mid-angle (degrees) of every slice; the pie starts at 12 o'clock and runs clockwise.
  const totalValue = data.reduce((sum, d) => sum + d.value, 0) || 1
  const midAngles: number[] = []
  let running = 0
  for (const d of data) {
    midAngles.push(90 - (360 * (running + d.value / 2)) / totalValue)
    running += d.value
  }

  // The label shows the same text as the hover tooltip, in full. It is only shortened
  // when even the smallest allowed pie couldn't sit beside it (very narrow screens).
  const maxLabelWidth = Math.max(110, pieAreaWidth - 2 * CANVAS_PADDING - 2 * MIN_RADIUS - 40)
  const labelTexts = new Map<number, string>()
  const smallInputs: SmallLabelInput[] = []
  data.forEach((d, index) => {
    if (d.share < SMALL_SLICE_PERCENT) {
      const text = labelTextToFit(d.name, formatCurrency(d.value), maxLabelWidth)
      labelTexts.set(index, text)
      smallInputs.push({ index, midAngle: midAngles[index], width: measureLabelWidth(text) })
    }
  })

  const { radius, layout } = fitPie(smallInputs, pieAreaWidth - 2 * CANVAS_PADDING, MAX_RADIUS, MIN_RADIUS)
  const canvasWidth = Math.ceil(layout.maxX - layout.minX + 2 * CANVAS_PADDING)
  const canvasHeight = Math.ceil(layout.maxY - layout.minY + 2 * CANVAS_PADDING)
  const cx = CANVAS_PADDING - layout.minX
  const cy = CANVAS_PADDING - layout.minY
  const centerFontSize = Math.max(12, Math.round(radius * 0.15))

  return (
    <div className="pie-card" ref={containerRef}>
      {error && (
        <p className="feedback feedback--error" role="alert">
          {error}
        </p>
      )}

      {!error && !summary && loading && <p className="loading-state">Loading chart…</p>}

      {!error && summary && data.length === 0 && (
        <p className="pie-empty">No expenses to chart for the current filters.</p>
      )}

      {!error && data.length > 0 && (
        <div
          className={`pie-body ${sideBySide ? '' : 'pie-body--stacked'} ${
            loading ? 'pie-body--stale' : ''
          }`}
          style={{ gap: sideBySide ? PIE_LEGEND_GAP : STACKED_GAP }}
        >
          <div className="pie-canvas" style={{ width: canvasWidth, height: canvasHeight }}>
            <PieChart width={canvasWidth} height={canvasHeight} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
              <Pie
                data={data}
                dataKey="value"
                nameKey="name"
                cx={cx}
                cy={cy}
                startAngle={90}
                endAngle={-270}
                innerRadius={radius * INNER_RATIO}
                outerRadius={radius}
                stroke="var(--paper)"
                strokeWidth={2}
                label={false}
                labelLine={false}
                isAnimationActive={false}
              >
                {data.map((d) => (
                  <Cell key={d.name} fill={d.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value) =>
                  formatCurrency(typeof value === 'number' ? value : Number(value ?? 0))
                }
              />
            </PieChart>

            {/* Leader lines + labels for small slices */}
            <svg
              className="pie-label-layer"
              width={canvasWidth}
              height={canvasHeight}
              aria-hidden="true"
            >
              {layout.items.map((it) => {
                const d = data[it.index]
                return (
                  <g key={d.name}>
                    <polyline
                      points={`${cx + it.anchorX},${cy + it.anchorY} ${cx + it.kneeX},${cy + it.labelY} ${cx + it.endX},${cy + it.labelY}`}
                      fill="none"
                      stroke={d.color}
                      strokeWidth={1.5}
                    />
                    <circle cx={cx + it.anchorX} cy={cy + it.anchorY} r={2.5} fill={d.color} />
                    <text
                      x={cx + it.textX}
                      y={cy + it.labelY}
                      textAnchor={it.side === 1 ? 'start' : 'end'}
                      dominantBaseline="central"
                      style={{ fill: 'var(--ink)', fontSize: LABEL_FONT_SIZE, fontWeight: 700 }}
                    >
                      {labelTexts.get(it.index)}
                    </text>
                  </g>
                )
              })}
            </svg>

            <div className="pie-center" style={{ left: cx, top: cy }} aria-hidden="true">
              <span className="pie-center-label">Total</span>
              <span className="pie-center-value" style={{ fontSize: centerFontSize }}>
                {formatCurrency(summary?.positive_total ?? 0)}
              </span>
            </div>
          </div>

          <ul className="pie-legend">
            {data.map((d) => (
              <li key={d.name} className="pie-legend-item">
                <span className="pie-swatch" style={{ background: d.color }} aria-hidden="true" />
                <span className="pie-legend-name" title={d.name}>
                  {d.name}
                </span>
                <span className="pie-legend-amount">{formatCurrency(d.value)}</span>
                <span className="pie-legend-share">{d.share.toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
