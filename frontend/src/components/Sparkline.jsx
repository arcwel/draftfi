// Tiny inline trend line for a category's monthly spend (D1). Pure SVG, no deps.
export default function Sparkline({ values, color = '#64748b', width = 64, height = 16 }) {
  if (!values || values.length < 2) return <span className="inline-block" style={{ width }} />
  const max = Math.max(...values, 1)
  const stepX = width / (values.length - 1)
  const points = values
    .map((v, i) => `${(i * stepX).toFixed(1)},${(height - (v / max) * (height - 2) - 1).toFixed(1)}`)
    .join(' ')
  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden="true">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}
