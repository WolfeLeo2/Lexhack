import { ChevronLeft, ChevronRight, CornerDownRight } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useState } from 'react'
import { PROVISIONS } from '../lib/data.ts'
import { play } from '../lib/feedback.ts'
import { resolve } from '../lib/status.ts'
import { Button, CourtWords, EVENT_LABEL, Part, StateTag, StatusStamp, shortCase, year } from './ui.tsx'

// What each step means, in plain words. The states and statuses themselves come from the real rules.
const STORY: Record<string, string> = {
  E18: 'The Court of Appeal says the death penalty can\'t be the only sentence for murder. That limits s.204.',
  E20: 'A five-judge Court of Appeal bench says Mutiso was decided per incuriam (it overlooked binding law): the death sentence is mandatory after all. A later court of the same rank pointing the other way displaces Mutiso.',
  E07: 'The Supreme Court declares the mandatory death sentence unconstitutional. It outranks the Court of Appeal, so Mwaura is displaced in turn. The death sentence survives, but judges must now have a choice.',
  E08: 'In further directions in the same case, the Supreme Court says its ruling covers murder only. That\'s an interpretation: it doesn\'t change the status, it travels with the ruling it explains.',
  E09: 'The Court of Appeal holds that s.8\'s minimum sentences must be read as leaving judges discretion. That\'s a read-down: the words stay, their force shrinks.',
  E11: 'Another Court of Appeal bench applies the Muruatetu reasoning to Sexual Offences Act sentences.',
  E12: 'The Court of Appeal goes further and treats the indeterminate life sentence in s.8(2) as unconstitutional.',
  E19: 'Another bench reads "life imprisonment" as thirty years.',
  E13: 'The Supreme Court reverses Mwangi on appeal. Because it outranks the Court of Appeal and points the other way, it also displaces Kilwake, which was never appealed, and, for now, Manyeso and Ayako.',
  E14: 'The Supreme Court reverses Manyeso directly on appeal.',
  E15: 'And it sets aside Ayako\'s thirty-year reading. Every Court of Appeal limit on s.8 is gone.',
  E06: 'The High Court declares s.194 invalid, but only "to the extent that" it goes beyond what the Constitution allows. The rest of the section stands.',
}

const CASES = [
  { n: '204', label: 'Penal Code s.204 (murder sentence)' },
  { n: '8', label: 'Sexual Offences Act s.8 (defilement)' },
  { n: '194', label: 'Penal Code s.194 (criminal defamation)' },
]

export function History() {
  const [which, setWhich] = useState('204')
  const [step, setStep] = useState(1)
  const reduce = useReducedMotion()
  const p = PROVISIONS.find((x) => x.provision.number === which && x.history.length)!
  const all = p.history
  const now = resolve(all.slice(0, step))
  const current = all[step - 1]
  const go = (s: number) => {
    setStep(Math.max(1, Math.min(all.length, s)))
    play('turn')
  }

  return (
    <Part
      id="never-yes-no"
      n={2}
      title="Why the answer is never yes or no"
      lede={
        <>
          <p>
            Two things make a simple "valid / invalid" answer wrong. Courts often strike down only part of a section
            ("to the extent that…"), and a section can have a history: limited by one court, restored by another,
            limited again. So LexHack stores every event separately and works the status out from the whole sequence,
            every time.
          </p>
          <p>Step through a real history below. The status is recalculated by the same rules the API uses.</p>
        </>
      }
    >
      <div className="flex flex-wrap gap-2" role="group" aria-label="Choose a section">
        {CASES.map((c) => (
          <Button
            key={c.n}
            variant="ghost"
            aria-pressed={which === c.n}
            onClick={() => {
              setWhich(c.n)
              setStep(1)
              play('tick')
            }}
          >
            {c.label}
          </Button>
        ))}
      </div>

      {/* the timeline rail */}
      <div className="mt-10 overflow-x-auto pb-2">
        <ol className="relative flex min-w-max items-start gap-0">
          {all.map((e, i) => {
            const past = i < step
            const st = now.history.find((h) => h.event_id === e.event_id)?.state
            return (
              <li key={e.event_id} className="relative w-36 shrink-0">
                <div className={`absolute top-[11px] right-0 left-0 h-[2px] ${i < step - 1 ? 'bg-ink' : 'bg-rule'}`} />
                <button
                  type="button"
                  onClick={() => go(i + 1)}
                  className="relative flex flex-col items-start text-left"
                  aria-current={i === step - 1 ? 'step' : undefined}
                >
                  <span
                    className={`grid h-6 w-6 place-items-center rounded-full border-2 text-[0.7rem] transition-colors ${
                      i === step - 1
                        ? 'border-seal bg-seal text-paper'
                        : past
                          ? 'border-ink bg-paper'
                          : 'border-rule bg-paper'
                    }`}
                  />
                  <span className={`mt-2 text-sm font-medium ${past ? '' : 'text-ink-2/60'}`}>
                    {year(e.effective_date)} {e.court?.replace('Court of Appeal', 'Appeal').replace(' Court', '')}
                  </span>
                  <span className={`text-sm ${past ? 'text-ink-2' : 'text-ink-2/50'}`}>{shortCase(e).split(' v ')[0]}</span>
                  {past && st && st !== 'in effect' && (
                    <span className="mt-0.5 text-xs text-seal">{st === 'reversed on appeal' ? 'reversed' : 'displaced'}</span>
                  )}
                </button>
              </li>
            )
          })}
        </ol>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <AnimatePresence mode="wait">
          <motion.div
            key={`${which}-${step}`}
            initial={{ opacity: 0, y: reduce ? 0 : 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22 }}
          >
            <p className="text-sm text-ink-2">
              Step {step} of {all.length}. {current.court}, {year(current.effective_date)}
            </p>
            <h3 className="statute mt-1 text-2xl">
              {EVENT_LABEL[current.event_type]}
              {current.scope === 'partial' && ', in part'}
            </h3>
            <p className="mt-3 max-w-[60ch]">{STORY[current.event_key ?? ''] ?? ''}</p>
            <CourtWords quote={current.operative_quote} mark={current.scope_text} className="mt-5 text-[1.08rem] text-ink" />
            <p className="mt-2 text-sm text-ink-2">
              {current.title}, para {current.source_paragraph}.{' '}
              <a className="link" href={current.source_url ?? '#'} target="_blank" rel="noreferrer">
                Read on Kenya Law
              </a>
            </p>
            <div className="mt-6 flex gap-2">
              <Button variant="ghost" onClick={() => go(step - 1)} disabled={step === 1}>
                <ChevronLeft size={18} aria-hidden /> Earlier
              </Button>
              <Button onClick={() => go(step + 1)} disabled={step === all.length}>
                Next ruling <ChevronRight size={18} aria-hidden />
              </Button>
            </div>
          </motion.div>
        </AnimatePresence>

        <div className="lg:border-l lg:border-rule lg:pl-10">
          <StatusStamp status={now.status} />
          <p className="mt-4 text-sm text-ink-2">After {step === 1 ? 'this ruling' : `these ${step} rulings`}:</p>
          <ul className="mt-2 space-y-3">
            {now.history.map((e) => {
              const by = now.history.find((h) => h.event_id === e.superseded_by)
              return (
                <li key={e.event_id} className="text-[0.95rem]">
                  <span className="font-medium">
                    {year(e.effective_date)} {shortCase(e)}
                  </span>
                  <span className="text-ink-2">: {EVENT_LABEL[e.event_type].toLowerCase()}. </span>
                  <StateTag state={e.state} />
                  {by && (
                    <span className="mt-0.5 flex items-center gap-1 text-sm text-ink-2">
                      <CornerDownRight size={14} aria-hidden /> by {shortCase(by)} ({year(by.effective_date)})
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
          <details className="mt-6 text-sm text-ink-2">
            <summary className="cursor-pointer font-medium text-ink">The rules, in full</summary>
            <ol className="mt-2 list-decimal space-y-1.5 pl-5">
              <li>An event stops counting when a higher court reverses it on appeal in the same case.</li>
              <li>
                It also stops counting when a later court of equal or higher rank points the other way (precedent). This
                is how the Supreme Court displaced Kilwake without an appeal.
              </li>
              <li>Interpretations never cancel anything. They travel with the ruling they explain.</li>
              <li>What still counts gives the status, and the status is always shown with the court's words.</li>
            </ol>
            <p className="mt-2">
              These are Kenya's rules. Other countries would need their own, so they live in their own module
              (api/status_ke.py).
            </p>
          </details>
        </div>
      </div>
    </Part>
  )
}
