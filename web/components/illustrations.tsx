import Link from 'next/link'
import type { Act } from '@/lib/api'
import { actHref, capLabel } from '@/lib/format'

/** An unmarked statute page: nothing pinned to it yet. */
export function BlankPage({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 96 112" className={className} aria-hidden fill="none">
      <path d="M8 4h60l20 20v84H8z" fill="var(--color-paper)" stroke="var(--color-ink-2)" strokeWidth="1.5" />
      <path d="M68 4v20h20" stroke="var(--color-ink-2)" strokeWidth="1.5" />
      {[34, 44, 54, 64, 74, 84].map((y, i) => (
        <line key={y} x1="18" x2={i % 3 === 2 ? 56 : 78} y1={y} y2={y} stroke="var(--color-rule)" strokeWidth="3" strokeLinecap="round" />
      ))}
      <text x="18" y="24" className="statute" fontSize="16" fill="var(--color-ink-2)">
        §
      </text>
    </svg>
  )
}

// Spine colours are bindings, not statuses: they just tell the books apart.
const BINDINGS = ['#1e5b47', '#8e2c48', '#18212b', '#4d5a66', '#2f4a5e', '#5a4632', '#1e5b47', '#6b2e3f']

/** The Acts we hold, as a shelf of bound volumes. Taller books have more archived versions. */
export function Shelf({ acts }: { acts: Act[] }) {
  return (
    <div className="overflow-x-auto pb-2">
      <ul className="flex min-w-max items-end gap-2 border-b-[6px] border-ink/80 px-2 pt-6">
        {acts.map((a, i) => {
          const h = 196 + Math.min(a.versions.length, 11) * 6
          const w = 46 + (a.title.length % 4) * 6
          const words = a.title.split(' ')
          const lines = a.title.length > 16 ? [words.slice(0, Math.ceil(words.length / 2)).join(' '), words.slice(Math.ceil(words.length / 2)).join(' ')] : [a.title]
          const ink = BINDINGS[i % BINDINGS.length]
          return (
            <li key={a.act_id}>
              <Link href={actHref(a.act_id)} className="group block outline-none" aria-label={`${a.title}, ${a.versions.length} versions`}>
                <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} className="spine block" aria-hidden>
                  <rect x="0.5" y="0.5" width={w - 1} height={h - 1} rx="3" fill={ink} />
                  <rect x="0.5" y="0.5" width="5" height={h - 1} rx="2" fill="#fff" opacity=".08" />
                  <line x1="4" x2={w - 4} y1="16" y2="16" stroke="var(--color-mark)" strokeOpacity=".7" />
                  <line x1="4" x2={w - 4} y1="20" y2="20" stroke="var(--color-mark)" strokeOpacity=".7" />
                  <line x1="4" x2={w - 4} y1={h - 34} y2={h - 34} stroke="var(--color-mark)" strokeOpacity=".7" />
                  <g transform={`translate(${w / 2 + (lines.length > 1 ? -7 : 0)} ${h - 44}) rotate(-90)`}>
                    {lines.map((l, j) => (
                      <text
                        key={j}
                        y={j * 15 + 5}
                        className="statute"
                        fontSize="13"
                        fill="#f1f3ee"
                        // squeeze a long line to fit the spine rather than let it run off the top
                        {...(l.length * 6.4 > h - 70 ? { textLength: h - 70, lengthAdjust: 'spacingAndGlyphs' } : {})}
                      >
                        {l}
                      </text>
                    ))}
                  </g>
                  <text x={w / 2} y={h - 14} textAnchor="middle" fontSize="10" fill="var(--color-mark)" opacity=".9">
                    {capLabel(a)}
                  </text>
                </svg>
              </Link>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
