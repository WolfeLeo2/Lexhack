import { useState } from 'react'
import { play } from '../lib/feedback.ts'
import { Button, Part } from './ui.tsx'

// A made-up judgment paragraph. Each span is a candidate; `real` says whether it's truly a statute citation.
const PARA: (string | { id: string; text: string; real: boolean })[] = [
  'The appellant was charged under ',
  { id: 'a', text: 'section 8(1) of the Sexual Offences Act', real: true },
  '. Counsel relied on ',
  { id: 'b', text: 'Article 50 of the Constitution', real: true },
  ' and on ',
  { id: 'c', text: 'section 333(2) of the Criminal Procedure Code', real: true },
  '. ',
  { id: 'd', text: 'Clause 4 of the lease', real: false },
  ' was not in issue. The trial court applied ',
  { id: 'e', text: 'section 8(2)', real: true },
  ', and under ',
  { id: 'f', text: 'Section 1 of the insurance policy', real: false },
  ' the claim failed. See also ',
  { id: 'g', text: 'sections 203', real: true },
  ' and ',
  { id: 'h', text: '204 of the Penal Code', real: true },
  '.',
]

const EXTRACTORS = {
  careful: { label: 'A careful extractor', finds: ['a', 'c', 'g', 'h'], note: 'Only flags citations that name their law. Never wrong, but it misses the bare "section 8(2)" and the Article.' },
  greedy: { label: 'A greedy extractor', finds: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'], note: 'Flags anything that looks like "word + number". Misses nothing, but it counts a lease and an insurance policy as law.' },
  ours: { label: 'Ours (patterns + LLM)', finds: ['a', 'b', 'c', 'e', 'f', 'g', 'h'], note: 'Close to what ours does. "Section 1 of an insurance policy" is a mistake it really made on the held-out set.' },
}
type Key = keyof typeof EXTRACTORS

const pct = (n: number, d: number) => (d ? Math.round((100 * n) / d) : 0)

export function Scoring() {
  const [ex, setEx] = useState<Key>('careful')
  const e = EXTRACTORS[ex]
  const cands = PARA.filter((p) => typeof p !== 'string')
  const tp = cands.filter((c) => c.real && e.finds.includes(c.id)).length
  const fp = cands.filter((c) => !c.real && e.finds.includes(c.id)).length
  const fn = cands.filter((c) => c.real && !e.finds.includes(c.id)).length

  return (
    <Part
      id="answer-key"
      n={5}
      title="Why an answer key"
      lede={
        <>
          <p>
            You can't tell whether a machine is right unless you already know the right answers for some cases. So
            before automating anything, we wrote them down by hand: 19 events, each read from the judgment, audited
            blind by a second reviewer, verified by a third, with the last call made by Leo. A script re-checks that
            every quote appears word for word in its judgment.
          </p>
          <p>
            The answer key does two jobs. It's the benchmark the pipeline is scored against, and it's reliable demo
            data while the full run finishes. Scoring uses two numbers. Try them on a toy example:
          </p>
        </>
      }
    >
      <div className="flex flex-wrap gap-2" role="group" aria-label="Choose an extractor">
        {(Object.keys(EXTRACTORS) as Key[]).map((k) => (
          <Button key={k} variant="ghost" aria-pressed={ex === k} onClick={() => (setEx(k), play('tick'))}>
            {EXTRACTORS[k].label}
          </Button>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div>
          <p className="statute rounded-md border border-rule bg-[#fbfcf9] p-6 text-[1.15rem] leading-[1.9]">
            {PARA.map((p, i) => {
              if (typeof p === 'string') return <span key={i}>{p}</span>
              const found = e.finds.includes(p.id)
              const cls = found && p.real ? 'bg-mark/80' : found ? 'bg-seal/15 outline outline-1 outline-seal text-seal' : p.real ? 'underline decoration-seal decoration-wavy decoration-1 underline-offset-4' : ''
              return (
                <span key={i} className={`rounded-[2px] px-0.5 transition-colors ${cls}`}>
                  {p.text}
                </span>
              )
            })}
          </p>
          <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm text-ink-2">
            <li><span className="bg-mark/80 px-1">found, and right</span></li>
            <li><span className="px-1 text-seal outline outline-1 outline-seal">found, but not law</span></li>
            <li><span className="underline decoration-seal decoration-wavy underline-offset-4">missed</span></li>
          </ul>
          <p className="mt-4 text-ink-2">{e.note}</p>
        </div>
        <dl className="grid grid-cols-2 gap-6 self-start">
          <div>
            <dt className="text-sm text-ink-2">Precision</dt>
            <dd className="statute text-5xl">{pct(tp, tp + fp)}%</dd>
            <dd className="mt-1 text-sm text-ink-2">
              {tp} right of {tp + fp} found. "When it flags something, is it right?"
            </dd>
          </div>
          <div>
            <dt className="text-sm text-ink-2">Recall</dt>
            <dd className="statute text-5xl">{pct(tp, tp + fn)}%</dd>
            <dd className="mt-1 text-sm text-ink-2">
              {tp} found of {tp + fn} real. "Does it find everything that's there?"
            </dd>
          </div>
        </dl>
      </div>

      <h3 className="statute mt-16 text-2xl">The real scores so far</h3>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full max-w-[72ch] text-left">
          <thead className="border-b border-ink text-sm text-ink-2">
            <tr>
              <th className="py-2 pr-4 font-medium">What's measured</th>
              <th className="py-2 pr-4 font-medium">Result</th>
              <th className="py-2 font-medium">How far to trust it</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule align-top">
            <tr>
              <td className="py-3 pr-4">Finding citations (step 5)</td>
              <td className="py-3 pr-4">98.1% precision, 98.1% recall</td>
              <td className="py-3 text-ink-2">Honest: 30 judgments the code had never seen, each labelled by two people independently (they agreed on 469 of 471).</td>
            </tr>
            <tr>
              <td className="py-3 pr-4">Finding events (step 6)</td>
              <td className="py-3 pr-4">19 of 19 answer-key events found, 18 with the right type</td>
              <td className="py-3 text-ink-2">Optimistic: the instructions were refined on these same 19. A review of random results from the full run will give the honest number.</td>
            </tr>
            <tr>
              <td className="py-3 pr-4">False alarms (step 6)</td>
              <td className="py-3 pr-4">0 of 6 non-events flagged</td>
              <td className="py-3 text-ink-2">The six judgments in negatives.csv mention a section without affecting it.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Part>
  )
}
