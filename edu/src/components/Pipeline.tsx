import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useState } from 'react'
import { PIPELINE } from '../lib/data.ts'
import { play } from '../lib/feedback.ts'
import { Part } from './ui.tsx'

const STATE = { done: 'Done', running: 'Running now', next: 'Next' }

export function Pipeline() {
  const [open, setOpen] = useState(5)
  const reduce = useReducedMotion()
  return (
    <Part
      id="how"
      n={3}
      title="How it's built"
      lede={
        <p>
          Nine steps, each feeding the next. Every step saves its output, so any one of them can be re-run without
          redoing the rest. The team splits the work in two: Leo owns the statutes, the database, the status
          rules and the API; Jackie owns the document side: citations in judgments and filings, the LLM pass for bare
          citations, and the evidence trail.
        </p>
      }
    >
      <ol className="border-l-2 border-rule">
        {PIPELINE.map((s, i) => {
          const isOpen = open === i
          return (
            <li key={s.title} className="relative pl-8">
              <span
                className={`absolute top-5 -left-[9px] h-4 w-4 rounded-full border-2 ${
                  s.state === 'done' ? 'border-ink bg-ink' : s.state === 'running' ? 'border-seal bg-paper' : 'border-rule bg-paper'
                }`}
                aria-hidden
              >
                {s.state === 'running' && !reduce && (
                  <motion.span
                    className="absolute inset-0 rounded-full bg-seal"
                    animate={{ opacity: [0.9, 0.2, 0.9] }}
                    transition={{ duration: 1.8, repeat: Infinity }}
                  />
                )}
              </span>
              <button
                type="button"
                onClick={() => {
                  setOpen(isOpen ? -1 : i)
                  play('tick')
                }}
                aria-expanded={isOpen}
                className="flex w-full flex-wrap items-baseline gap-x-4 gap-y-1 py-4 text-left"
              >
                <span className="statute text-xl">
                  <span className="text-ink-2/60">{i + 1}. </span>
                  {s.title}
                </span>
                <span className={`text-sm ${s.state === 'running' ? 'text-seal' : 'text-ink-2'}`}>{STATE[s.state]}</span>
              </button>
              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: reduce ? 0 : 0.25 }}
                    className="overflow-hidden"
                  >
                    <div className="max-w-[68ch] pb-6">
                      <p>{s.plain}</p>
                      <dl className="mt-4 grid grid-cols-1 gap-3 text-[0.95rem] sm:grid-cols-[7rem_1fr]">
                        <dt className="text-ink-2">Takes in</dt>
                        <dd>{s.in}</dd>
                        <dt className="text-ink-2">Produces</dt>
                        <dd>{s.out}</dd>
                        {s.files && (
                          <>
                            <dt className="text-ink-2">In the repo</dt>
                            <dd className="font-mono text-sm">{s.files}</dd>
                          </>
                        )}
                      </dl>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </li>
          )
        })}
      </ol>

      <div className="mt-12 grid grid-cols-1 gap-8 md:grid-cols-2">
        <div className="rounded-md bg-panel p-6">
          <h3 className="font-semibold">Why the Internet Archive, not Kenya Law?</h3>
          <p className="mt-2 text-ink-2">
            Kenya Law blocks automated downloads. The Internet Archive keeps public copies of its pages, so we took
            everything from there. It holds about 10% of all Kenyan judgments, so our 16,419 judgments are a large
            sample, not the complete record. Missing pages can be saved by hand.
          </p>
        </div>
        <div className="rounded-md bg-panel p-6">
          <h3 className="font-semibold">Where the AI is, and where it isn't</h3>
          <p className="mt-2 text-ink-2">
            Patterns do most of the citation finding. A language model handles what patterns can't: which law a bare
            "section 39" means, and what a court did to a section. It never gets the last word on quotes: every quote
            it returns is checked against the judgment, character for character, and dropped if it doesn't match.
          </p>
        </div>
      </div>
    </Part>
  )
}
