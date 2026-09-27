import { FileSpreadsheet, Table2 } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { TABLES } from '../lib/data.ts'
import { play } from '../lib/feedback.ts'
import { Part } from './ui.tsx'

// Where each table sits on the map (viewBox 760 x 420): statutes left, events middle, judgments right.
const POS: Record<string, [number, number]> = {
  acts: [110, 70],
  act_versions: [110, 170],
  provisions: [110, 270],
  provision_texts: [110, 370],
  'events.csv': [300, 60],
  'negatives.csv': [470, 60],
  citation_events: [385, 200],
  event_runs: [470, 330],
  'events_review.csv': [270, 330],
  judgments: [650, 130],
  citation_mentions: [650, 250],
  'mentions_gold.csv': [650, 370],
}
const LABEL: Record<string, string> = {
  'events.csv': 'answer key',
  'negatives.csv': 'non-events',
  'mentions_gold.csv': 'citation key',
  'events_review.csv': 'blind reviews',
}
const W = 150
const H = 38

const QUESTIONS = [
  [
    'Why keep mentions and events apart?',
    'A mention only says a judgment cites a section. An event says the court did something to it. Most judgments that mention s.204 are murder trials that simply apply it. Mixing the two would make every murder trial look like a ruling on the death penalty.',
  ],
  [
    'Why is status never stored?',
    'Because it changes when a new ruling arrives. Storing each event and working the status out on request means one new row can update a section\'s status correctly, including undoing older rulings.',
  ],
  [
    'Why insist on exact quotes?',
    'The tool\'s whole value is that you can trust it. A paraphrase can quietly change what a court said. An exact quote with a paragraph number can be checked by anyone in seconds.',
  ],
  [
    'Why put "ke" in every ID?',
    'Every ID starts with the country, so other countries\' laws could be added later without clashing with Kenya\'s.',
  ],
  [
    'Why hide the machine-found events by default?',
    'About one in five is wrong, and a wrong event can flip a section\'s status. A tool people trust about the law can\'t show guesses as facts. So the API returns only verified events unless asked, labels the rest unverified, and never returns events the second-pass checker failed. A review queue will let a person promote good leads to verified.',
  ],
  [
    'Where does the data live for each of us?',
    'Code is in git. Data is in $LEXHACK_DATA on each laptop (about 880 MB: raw pages, parsed files, LLM and embedding caches), shared through Cloudflare R2 with scripts/sync.sh (sync.ps1 on Windows). Pull before working, push after; it only copies, never deletes. The shared Neon database holds the tables.',
  ],
  [
    'Why do judgments stay on disk?',
    'Their full text is about 360 MB, and the free database plan holds about 512 MB. The database keeps each judgment\'s details and a pointer to its file.',
  ],
]

export function DataMap() {
  const [sel, setSel] = useState('citation_events')
  const t = TABLES.find((x) => x.id === sel)!
  const edges = TABLES.flatMap((x) => x.links.map((to) => [x.id, to] as const))
  const lit = (a: string, b: string) => a === sel || b === sel

  return (
    <Part
      id="data"
      n={4}
      title="The data: tables and files"
      lede={
        <p>
          Everything lives in one Postgres database, plus a few CSV files we keep in the repo and edit by hand. Select a
          box to see what it holds, why it exists and what one row looks like. Lines show which tables point at which.
        </p>
      }
    >
      <div className="grid grid-cols-1 gap-10 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div>
          <svg viewBox="0 0 760 420" className="w-full" role="group" aria-label="Map of the tables and files">
            {[
              [110, 'Statutes'],
              [385, 'Events'],
              [650, 'Judgments'],
            ].map(([x, l]) => (
              <text key={l} x={x} y={16} textAnchor="middle" className="fill-ink-2 text-[13px]">
                {l}
              </text>
            ))}
            {edges.map(([a, b]) => {
              const [x1, y1] = POS[a]
              const [x2, y2] = POS[b]
              const d =
                a === b
                  ? `M${x1 + W / 2} ${y1 - 8} C ${x1 + W / 2 + 50} ${y1 - 40}, ${x1 + W / 2 + 50} ${y1 + 40}, ${x1 + W / 2} ${y1 + 8}`
                  : `M${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}`
              return (
                <path
                  key={a + b}
                  d={d}
                  fill="none"
                  stroke={lit(a, b) ? 'var(--color-seal)' : 'var(--color-rule)'}
                  strokeWidth={lit(a, b) ? 2 : 1.5}
                  strokeDasharray={a.endsWith('.csv') ? '5 4' : undefined}
                  className="transition-[stroke] duration-200"
                />
              )
            })}
            {Object.entries(POS).map(([id, [x, y]]) => {
              const on = id === sel
              const csv = id.endsWith('.csv')
              return (
                <g
                  key={id}
                  role="button"
                  tabIndex={0}
                  aria-pressed={on}
                  aria-label={id}
                  onClick={() => (setSel(id), play('tick'))}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setSel(id), play('tick'))}
                  className="cursor-pointer outline-none [&:focus-visible>rect]:stroke-gazette"
                >
                  <rect
                    x={x - W / 2}
                    y={y - H / 2}
                    width={W}
                    height={H}
                    rx={csv ? 2 : 6}
                    className={`transition-colors ${on ? 'fill-ink' : csv ? 'fill-panel' : 'fill-paper'}`}
                    stroke={on ? 'var(--color-ink)' : 'var(--color-ink-2)'}
                    strokeDasharray={csv ? '4 3' : undefined}
                    strokeWidth={1.2}
                  />
                  <text x={x} y={y + (LABEL[id] ? -2 : 5)} textAnchor="middle" className={`font-mono text-[12.5px] ${on ? 'fill-paper' : 'fill-ink'}`}>
                    {id}
                  </text>
                  {LABEL[id] && (
                    <text x={x} y={y + 12} textAnchor="middle" className={`text-[10.5px] ${on ? 'fill-paper/80' : 'fill-ink-2'}`}>
                      {LABEL[id]}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
          <div className="mt-3 flex flex-wrap gap-1.5 md:hidden" role="group" aria-label="Choose a table">
            {Object.keys(POS).map((id) => (
              <button
                key={id}
                type="button"
                aria-pressed={id === sel}
                onClick={() => (setSel(id), play('tick'))}
                className="rounded border border-rule px-2 py-1 font-mono text-xs aria-pressed:border-ink aria-pressed:bg-ink aria-pressed:text-paper"
              >
                {id}
              </button>
            ))}
          </div>
          <p className="mt-2 text-sm text-ink-2">
            Solid boxes are database tables. Dashed boxes are CSV files in <span className="font-mono">ground_truth/</span>;
            dashed lines mean "is used to check".
          </p>
        </div>

        <AnimatePresence mode="wait">
          <motion.article
            key={sel}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            aria-live="polite"
          >
            <div className="flex items-center gap-2 text-ink-2">
              {t.kind === 'csv' ? <FileSpreadsheet size={18} aria-hidden /> : <Table2 size={18} aria-hidden />}
              <span className="text-sm">
                {t.kind === 'csv' ? 'CSV file' : 'Database table'}, {t.rows} rows
              </span>
            </div>
            <h3 className="mt-1 font-mono text-xl">{t.id}</h3>
            <p className="statute mt-3 text-xl">{t.what}</p>
            <p className="mt-3">
              <span className="font-semibold">Why it exists. </span>
              {t.why}
            </p>
            <p className="mt-2 text-[0.95rem] text-ink-2">
              <span className="font-medium text-ink">Made by: </span>
              {t.madeBy}
            </p>
            <div className="mt-5 overflow-x-auto rounded-md border border-rule">
              <table className="w-full text-left text-[0.92rem]">
                <thead className="bg-panel text-ink-2">
                  <tr>
                    <th className="px-3 py-2 font-medium">Column</th>
                    <th className="px-3 py-2 font-medium">Holds, with an example</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {t.columns.map(([c, m, ex]) => (
                    <tr key={c}>
                      <td className="w-[38%] px-3 py-2.5 align-top font-mono text-[0.8rem] break-words">{c}</td>
                      <td className="px-3 py-2.5 align-top">
                        {m}
                        <span className="mt-0.5 block font-mono text-[0.76rem] break-words text-ink-2">{ex}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.article>
        </AnimatePresence>
      </div>

      <div className="mt-14 max-w-[72ch] divide-y divide-rule border-y border-rule">
        {QUESTIONS.map(([q, a]) => (
          <details key={q} className="group py-4" onToggle={(e) => (e.currentTarget as HTMLDetailsElement).open && play('tick')}>
            <summary className="cursor-pointer list-none font-medium marker:hidden">
              <span className="mr-2 inline-block text-ink-2 transition-transform group-open:rotate-90">›</span>
              {q}
            </summary>
            <p className="mt-2 pl-5 text-ink-2">{a}</p>
          </details>
        ))}
      </div>
    </Part>
  )
}
