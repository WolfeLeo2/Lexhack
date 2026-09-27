'use client'
import { useState } from 'react'
import type { CourtEvent } from '@/lib/api'
import { EVENT_LABEL, rank, shortCase } from '@/lib/format'

// A section's court history drawn as the court hierarchy over time: one lane per rank, one mark per ruling, and an
// arrow from each ruling to the earlier one it reversed or displaced. Marks link to the full entry below the chart.
const W = 760
const LEFT = 150
const RIGHT = 30
const LANE: Record<number, number> = { 3: 44, 2: 108, 1: 172 }
const LANE_NAME: Record<number, string> = { 3: 'Supreme Court', 2: 'Court of Appeal', 1: 'High Court' }
const H = 222

const t = (d: string) => new Date(d + 'T00:00:00').getTime()

export function Lineage({ events }: { events: CourtEvent[] }) {
  const [active, setActive] = useState<number | null>(null)
  const dated = events.filter((e) => e.effective_date).sort((a, b) => t(a.effective_date!) - t(b.effective_date!))
  if (!dated.length) return null

  const lo = new Date(t(dated[0].effective_date!)).getFullYear()
  const hi = new Date(t(dated.at(-1)!.effective_date!)).getFullYear() + 1
  const span = Math.max(1, hi - lo)
  const x = (d: string) => {
    const dt = new Date(d + 'T00:00:00')
    const yf = dt.getFullYear() + (dt.getMonth() * 30 + dt.getDate()) / 366
    return LEFT + ((yf - lo) / span) * (W - LEFT - RIGHT)
  }
  const pos = new Map<number, { x: number; y: number }>()
  for (const e of dated) {
    let px = x(e.effective_date!)
    const py = LANE[rank(e.court)]
    // two rulings in the same court within days of each other: nudge the later one so both stay visible
    for (const p of pos.values()) if (p.y === py && Math.abs(p.x - px) < 20) px = p.x + 20
    pos.set(e.event_id, { x: px, y: py })
  }
  const ticks = Array.from({ length: span + 1 }, (_, i) => lo + i).filter((y, _, a) => a.length <= 12 || (y - lo) % Math.ceil(a.length / 10) === 0)
  const order = new Map(dated.map((e, i) => [e.event_id, i]))
  const step = 0.18   // seconds between rulings in the load sequence (globals.css .lineage-*)
  const edges = dated.filter((e) => e.superseded_by != null && pos.has(e.superseded_by))
  const act = dated.find((e) => e.event_id === active)

  return (
    <figure className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[640px]" role="img" aria-labelledby="lineage-title">
        <title id="lineage-title">
          {`Court rulings on this section over time, ${dated.length} in all. Arrows point from a ruling to the earlier ruling it reversed or displaced.`}
        </title>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 1 9 5 0 9" fill="none" stroke="var(--color-ink-2)" strokeWidth="1.6" />
          </marker>
        </defs>

        {[3, 2, 1].map((r) => (
          <g key={r}>
            <line x1={LEFT - 12} x2={W - RIGHT + 10} y1={LANE[r]} y2={LANE[r]} stroke="var(--color-rule)" strokeDasharray="2 5" />
            <text x={LEFT - 22} y={LANE[r] + 5} textAnchor="end" className="statute fill-ink-2 text-[14px]">
              {LANE_NAME[r]}
            </text>
          </g>
        ))}
        <line x1={LEFT - 12} x2={W - RIGHT + 10} y1={H - 22} y2={H - 22} stroke="var(--color-rule)" />
        {ticks.map((y) => {
          const tx = LEFT + ((y - lo) / span) * (W - LEFT - RIGHT)
          return (
            <g key={y}>
              <line x1={tx} x2={tx} y1={H - 26} y2={H - 18} stroke="var(--color-ink-2)" strokeOpacity=".5" />
              <text x={tx} y={H - 4} textAnchor="middle" className="fill-ink-2 text-[11px] tabular-nums">
                {y}
              </text>
            </g>
          )
        })}

        {edges.map((e) => {
          const to = pos.get(e.event_id)!
          const from = pos.get(e.superseded_by!)!
          const lift = Math.min(46, 18 + Math.abs(from.x - to.x) / 6)
          const d = `M${from.x - 7} ${from.y - 6} C${from.x - 20} ${Math.min(from.y, to.y) - lift}, ${to.x + 20} ${Math.min(from.y, to.y) - lift}, ${to.x + 6} ${to.y - 8}`
          const reversed = e.state === 'reversed on appeal'
          return (
            <path
              key={`edge-${e.event_id}`}
              d={d}
              // pathLength rescales dash units, so only the solid (reversed) arrow uses it to draw itself on
              pathLength={reversed ? 1 : undefined}
              className={reversed ? 'lineage-edge' : 'lineage-edge-dashed'}
              fill="none"
              stroke="var(--color-ink-2)"
              strokeWidth="1.3"
              strokeDasharray={reversed ? undefined : '4 4'}
              markerEnd="url(#arrow)"
              style={{
                animationDelay: `${step * (order.get(e.superseded_by!)! + 1)}s`,
                opacity: active == null || active === e.event_id || active === e.superseded_by ? 1 : 0.25,
              }}
            />
          )
        })}

        {dated.map((e) => {
          const p = pos.get(e.event_id)!
          const live = e.state === 'in effect'
          const dim = active != null && active !== e.event_id
          const stroke = live ? 'var(--color-seal)' : 'var(--color-ink-2)'
          return (
            <a
              key={e.event_id}
              href={`#e-${e.event_id}`}
              aria-label={`${EVENT_LABEL[e.event_type] ?? e.event_type}: ${shortCase(e.title)}, ${e.court}, ${e.effective_date?.slice(0, 4)}. ${e.state}.`}
              onMouseEnter={() => setActive(e.event_id)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(e.event_id)}
              onBlur={() => setActive(null)}
              style={{ opacity: dim ? 0.35 : 1, transition: 'opacity 0.2s' }}
              className="cursor-pointer outline-none"
            >
              <g className="lineage-node" style={{ transformOrigin: `${p.x}px ${p.y}px`, animationDelay: `${step * order.get(e.event_id)!}s` }}>
              <circle cx={p.x} cy={p.y} r="16" fill="transparent" />
              {e.event_type === 'interpreted' ? (
                <rect
                  x={p.x - 5.5}
                  y={p.y - 5.5}
                  width="11"
                  height="11"
                  transform={`rotate(45 ${p.x} ${p.y})`}
                  fill="var(--color-paper)"
                  stroke="var(--color-gazette)"
                  strokeWidth="2"
                  strokeDasharray={e.verified ? undefined : '2 2'}
                />
              ) : (
                <circle
                  cx={p.x}
                  cy={p.y}
                  r="7.5"
                  fill={live && e.verified ? 'var(--color-seal)' : 'var(--color-paper)'}
                  stroke={stroke}
                  strokeWidth="2"
                  strokeDasharray={e.verified ? undefined : '2.5 2'}
                />
              )}
              {!live && <line x1={p.x - 6} y1={p.y + 6} x2={p.x + 6} y2={p.y - 6} stroke="var(--color-ink-2)" strokeWidth="1.6" />}
              {active === e.event_id && (
                <circle cx={p.x} cy={p.y} r="12" fill="none" stroke="var(--color-gazette)" strokeWidth="1.5" />
              )}
              </g>
            </a>
          )
        })}
      </svg>
      <figcaption className="mt-2 min-h-[3.2rem] text-[0.95rem] text-ink-2" aria-live="polite">
        {act ? (
          <>
            <span className="text-ink">{shortCase(act.title)}</span>, {act.court}, {act.effective_date?.slice(0, 4)}.{' '}
            {EVENT_LABEL[act.event_type] ?? act.event_type}; {act.state === 'in effect' ? 'still counts' : act.state}.
          </>
        ) : (
          <Legend />
        )}
      </figcaption>
    </figure>
  )
}

function Legend() {
  return (
    <span className="flex flex-wrap items-center gap-x-5 gap-y-1">
      <span className="inline-flex items-center gap-1.5">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
          <circle cx="8" cy="8" r="6" fill="var(--color-seal)" />
        </svg>
        Ruling that still counts
      </span>
      <span className="inline-flex items-center gap-1.5">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
          <circle cx="8" cy="8" r="6" fill="none" stroke="var(--color-ink-2)" strokeWidth="1.8" />
          <line x1="3.5" y1="12.5" x2="12.5" y2="3.5" stroke="var(--color-ink-2)" strokeWidth="1.5" />
        </svg>
        Reversed or displaced
      </span>
      <span className="inline-flex items-center gap-1.5">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
          <rect x="4" y="4" width="8" height="8" transform="rotate(45 8 8)" fill="none" stroke="var(--color-gazette)" strokeWidth="1.8" />
        </svg>
        Interpretation
      </span>
      <span>Solid arrow: reversed on appeal. Dashed: displaced by a later, equal or higher court.</span>
    </span>
  )
}
