export const LABEL_FONT_SIZE = 13
/** Minimum vertical distance between small-slice labels, in px. */
export const LABEL_GAP = 18

const RAD = Math.PI / 180
const LINE_OFFSET = 22 // how far outside the circle a label's ideal position is
const KNEE_OFFSET = 18 // how far outside the circle (at its own height) the line bends
const TAIL = 12 // length of the horizontal part of the line
const TEXT_PADDING = 4

export interface SmallLabelInput {
  index: number
  /** Mid-angle of the slice in degrees (pie runs clockwise from 12 o'clock). */
  midAngle: number
  /** Rendered width of the label text in px. */
  width: number
}

export interface LabelItem {
  index: number
  side: 1 | -1
  anchorX: number
  anchorY: number
  kneeX: number
  endX: number
  textX: number
  labelY: number
  width: number
}

export interface LabelLayout {
  /** All coordinates are relative to the pie's centre. */
  items: LabelItem[]
  minX: number
  maxX: number
  minY: number
  maxY: number
}

let measureContext: CanvasRenderingContext2D | null | undefined

/** Width of a label's text in px, measured with the page's font. */
export function measureLabelWidth(text: string): number {
  if (measureContext === undefined) {
    measureContext =
      typeof document !== 'undefined' ? document.createElement('canvas').getContext('2d') : null
  }
  if (measureContext) {
    const family = getComputedStyle(document.body).fontFamily || 'sans-serif'
    measureContext.font = `700 ${LABEL_FONT_SIZE}px ${family}`
    return Math.ceil(measureContext.measureText(text).width * 1.04) + 2
  }
  return Math.ceil(text.length * LABEL_FONT_SIZE * 0.62)
}

/**
 * "Name: $amount", shortened with an ellipsis (on the name only) when the full
 * text is wider than maxWidth. Only happens when there is genuinely no room.
 */
export function labelTextToFit(name: string, amount: string, maxWidth: number): string {
  const full = `${name}: ${amount}`
  if (measureLabelWidth(full) <= maxWidth) return full
  for (let n = name.length - 1; n > 3; n--) {
    const text = `${name.slice(0, n).trimEnd()}…: ${amount}`
    if (measureLabelWidth(text) <= maxWidth) return text
  }
  return `${name.slice(0, 3)}…: ${amount}`
}

/**
 * Place a leader-line label for every small slice so no two overlap. Labels sit
 * outside the circle; clusters are spread apart vertically (upwards above the
 * centre line, downwards below it). Also reports the bounding box of everything
 * drawn so the caller can size the chart to fit.
 */
export function layoutSmallLabels(radius: number, small: SmallLabelInput[]): LabelLayout {
  const items: LabelItem[] = small.map(({ index, midAngle, width }) => {
    const rad = -midAngle * RAD
    const cos = Math.cos(rad)
    const sin = Math.sin(rad)
    return {
      index,
      side: cos >= 0 ? 1 : -1,
      anchorX: radius * cos,
      anchorY: radius * sin,
      kneeX: 0,
      endX: 0,
      textX: 0,
      labelY: (radius + LINE_OFFSET) * sin,
      width,
    }
  })

  for (const side of [1, -1] as const) {
    const sideItems = items.filter((it) => it.side === side)
    const upper = sideItems.filter((it) => it.labelY < 0).sort((a, b) => b.labelY - a.labelY)
    const lower = sideItems.filter((it) => it.labelY >= 0).sort((a, b) => a.labelY - b.labelY)
    for (let i = 1; i < upper.length; i++) {
      upper[i].labelY = Math.min(upper[i].labelY, upper[i - 1].labelY - LABEL_GAP)
    }
    for (let i = 1; i < lower.length; i++) {
      lower[i].labelY = Math.max(lower[i].labelY, lower[i - 1].labelY + LABEL_GAP)
    }
  }

  let minX = -radius
  let maxX = radius
  let minY = -radius
  let maxY = radius
  for (const it of items) {
    // Keep the bend outside the circle at the label's own height.
    // Use the label's edge that is closest to the centre line, where the circle is widest.
    const nearY =
      it.labelY < 0
        ? Math.min(it.labelY + LABEL_FONT_SIZE / 2, 0)
        : Math.max(it.labelY - LABEL_FONT_SIZE / 2, 0)
    const halfWidth = Math.sqrt(Math.max(radius * radius - nearY * nearY, 0))
    it.kneeX = it.side * (halfWidth + KNEE_OFFSET)
    it.endX = it.kneeX + it.side * TAIL
    it.textX = it.endX + it.side * TEXT_PADDING
    const textEdge = it.textX + it.side * it.width
    minX = Math.min(minX, textEdge)
    maxX = Math.max(maxX, textEdge)
    minY = Math.min(minY, it.labelY - LABEL_FONT_SIZE)
    maxY = Math.max(maxY, it.labelY + LABEL_FONT_SIZE)
  }

  return { items, minX, maxX, minY, maxY }
}

/**
 * Pick the largest radius (<= maxRadius) at which the circle plus all labels fit
 * in availableWidth, and return it with its layout.
 */
export function fitPie(
  small: SmallLabelInput[],
  availableWidth: number,
  maxRadius: number,
  minRadius: number,
): { radius: number; layout: LabelLayout } {
  let radius = maxRadius
  let layout = layoutSmallLabels(radius, small)
  while (radius > minRadius && layout.maxX - layout.minX > availableWidth) {
    radius -= 4
    layout = layoutSmallLabels(radius, small)
  }
  return { radius, layout }
}
