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

/** A filing under the magnifying glass: the glass travels down the page and each citation it passes is marked, one
 * of them with the proofreader's wavy line. Plays once on load (globals.css: .glass, .glass-mark, .glass-squiggle). */
export function FilingUnderGlass({ className = '' }: { className?: string }) {
  const rules = [70, 86, 102, 118, 134, 150, 166, 182, 198, 214]
  return (
    <svg viewBox="0 0 320 270" className={className} aria-hidden fill="none">
      <g transform="rotate(-2 150 140)">
        <path d="M44 14h150l30 30v214H44z" fill="var(--color-paper)" stroke="var(--color-ink-2)" strokeWidth="1.5" />
        <path d="M194 14v30h30" stroke="var(--color-ink-2)" strokeWidth="1.5" />
        <line x1="70" x2="170" y1="40" y2="40" stroke="var(--color-ink-2)" strokeWidth="4" strokeLinecap="round" />
        <line x1="92" x2="148" y1="52" y2="52" stroke="var(--color-ink-2)" strokeWidth="2.5" strokeLinecap="round" />
        {rules.map((y, i) => (
          <line key={y} x1="70" x2={i % 4 === 3 ? 150 : 200} y1={y} y2={y} stroke="var(--color-rule)" strokeWidth="3" strokeLinecap="round" />
        ))}
        <rect x="68" y="95.5" width="62" height="13" rx="2" fill="var(--hl)" className="glass-mark" style={{ ['--i' as string]: 0 }} />
        <rect x="120" y="159.5" width="80" height="13" rx="2" fill="var(--hl)" className="glass-mark" style={{ ['--i' as string]: 2 }} />
        <path
          d="M72 144 q5 -4 10 0 t10 0 t10 0 t10 0 t10 0 t10 0 t10 0"
          pathLength={1}
          stroke="var(--color-seal)"
          strokeWidth="2"
          strokeLinecap="round"
          className="glass-squiggle"
        />
        <line x1="56" x2="56" y1="24" y2="250" stroke="var(--color-seal)" strokeOpacity=".35" />
      </g>
      <g className="glass">
        <circle cx="0" cy="0" r="34" fill="var(--color-paper)" fillOpacity=".55" stroke="var(--color-ink)" strokeWidth="5" />
        <path d="M-18 -16 a24 24 0 0 1 14 -10" stroke="#fff" strokeOpacity=".7" strokeWidth="3" strokeLinecap="round" />
        <text x="0" y="6" textAnchor="middle" className="statute" fontSize="15" fill="var(--color-ink)">
          [2017]
        </text>
        <line x1="25" y1="25" x2="52" y2="52" stroke="var(--color-ink)" strokeWidth="9" strokeLinecap="round" />
      </g>
    </svg>
  )
}

/** Small marks for the report: a judgment (case), the section sign (section), quotation marks (quote). */
export function KindIcon({ kind, className = 'h-5 w-5' }: { kind: 'case' | 'section' | 'quote'; className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={className} aria-hidden fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
      {kind === 'case' && (
        <>
          <path d="M4 3h9l3 3v11H4z" />
          <path d="M7 8h6M7 11h6M7 14h4" />
        </>
      )}
      {kind === 'section' && (
        <text x="10" y="15" textAnchor="middle" fontSize="15" fill="currentColor" stroke="none" className="statute">
          §
        </text>
      )}
      {kind === 'quote' && (
        <text x="10" y="18" textAnchor="middle" fontSize="20" fill="currentColor" stroke="none" className="statute">
          “
        </text>
      )}
    </svg>
  )
}

/** A question put to the statute book: the bubble pops up, then the court's line is marked on the page as the
 * answer (globals.css: .ask-bubble, .glass-mark). */
export function QuestionToTheBook({ className = '' }: { className?: string }) {
  const rules = [64, 80, 96, 112, 128, 144, 160, 176]
  return (
    <svg viewBox="0 0 320 240" className={className} aria-hidden fill="none">
      <g transform="rotate(2 150 130)">
        <path d="M96 30h132l26 26v168H96z" fill="var(--color-paper)" stroke="var(--color-ink-2)" strokeWidth="1.5" />
        <path d="M228 30v26h26" stroke="var(--color-ink-2)" strokeWidth="1.5" />
        <text x="116" y="54" className="statute" fontSize="16" fill="var(--color-ink-2)">
          § 204
        </text>
        {rules.map((y, i) => (
          <line key={y} x1="116" x2={i % 3 === 2 ? 196 : 234} y1={y + 10} y2={y + 10} stroke="var(--color-rule)" strokeWidth="3" strokeLinecap="round" />
        ))}
        <rect x="114" y="131.5" width="104" height="13" rx="2" fill="var(--hl)" className="glass-mark" style={{ ['--i' as string]: 1.4 }} />
        <path d="M112 200 h60" stroke="var(--color-seal)" strokeWidth="2" strokeLinecap="round" pathLength={1} className="glass-squiggle" />
      </g>
      <g className="ask-bubble">
        <path
          d="M30 40h92a12 12 0 0 1 12 12v40a12 12 0 0 1-12 12H66l-18 18v-18H30a12 12 0 0 1-12-12V52a12 12 0 0 1 12-12z"
          fill="var(--color-note)"
          stroke="var(--color-note-rule)"
          strokeWidth="1.5"
        />
        <text x="76" y="82" textAnchor="middle" className="statute" fontSize="26" fontStyle="italic" fill="var(--color-ink)">
          still law?
        </text>
      </g>
    </svg>
  )
}
