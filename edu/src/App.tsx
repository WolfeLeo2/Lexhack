import { Volume2, VolumeX } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DataMap } from './components/DataMap.tsx'
import { Glossary } from './components/Glossary.tsx'
import { Hero } from './components/Hero.tsx'
import { History } from './components/History.tsx'
import { Pipeline } from './components/Pipeline.tsx'
import { Playground } from './components/Playground.tsx'
import { Problem } from './components/Problem.tsx'
import { Scoring } from './components/Scoring.tsx'
import { useSound } from './lib/feedback.ts'

const CONTENTS = [
  ['problem', 'The problem'],
  ['never-yes-no', 'Never yes or no'],
  ['how', "How it's built"],
  ['data', 'The data'],
  ['answer-key', 'Why an answer key'],
  ['try', 'Try it'],
  ['glossary', 'Glossary'],
]

function useCurrentSection() {
  const [cur, setCur] = useState('')
  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setCur(e.target.id)),
      { rootMargin: '-35% 0px -60% 0px' },
    )
    CONTENTS.forEach(([id]) => {
      const el = document.getElementById(id)
      if (el) io.observe(el)
    })
    return () => io.disconnect()
  }, [])
  return cur
}

export default function App() {
  const { enabled, toggle } = useSound()
  const cur = useCurrentSection()

  return (
    <>
      <a href="#problem" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:bg-paper focus:p-2">
        Skip to content
      </a>
      <div className="sticky top-0 z-30 border-b border-rule bg-paper/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[88rem] items-center justify-between px-5 sm:px-8">
          <a href="#top" className="statute text-xl font-medium">
            LexHack
          </a>
          <nav className="hidden gap-5 text-sm md:flex lg:hidden" aria-label="Contents">
            {CONTENTS.map(([id, l]) => (
              <a key={id} href={`#${id}`} className={cur === id ? 'text-ink' : 'text-ink-2 hover:text-ink'}>
                {l}
              </a>
            ))}
          </nav>
          <button
            type="button"
            onClick={toggle}
            aria-pressed={enabled}
            className="flex items-center gap-2 rounded-md px-2 py-1 text-sm text-ink-2 hover:text-ink"
          >
            {enabled ? <Volume2 size={18} aria-hidden /> : <VolumeX size={18} aria-hidden />}
            {enabled ? 'Sound on' : 'Sound off'}
          </button>
        </div>
      </div>

      <div id="top" className="mx-auto grid grid-cols-1 max-w-[88rem] px-5 sm:px-8 lg:grid-cols-[12rem_minmax(0,1fr)] lg:gap-16">
        <aside className="hidden lg:block">
          <nav className="sticky top-24 pt-16" aria-label="Contents">
            <p className="statute text-ink-2">Arrangement of parts</p>
            <ol className="mt-3 space-y-1.5 text-[0.95rem]">
              {CONTENTS.map(([id, l], i) => (
                <li key={id}>
                  <a
                    href={`#${id}`}
                    aria-current={cur === id ? 'location' : undefined}
                    className="flex gap-2 border-l-2 border-transparent py-0.5 pl-3 text-ink-2 hover:text-ink aria-[current=location]:border-seal aria-[current=location]:text-ink"
                  >
                    <span className="w-4 text-ink-2/60">{i + 1}.</span>
                    {l}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        </aside>

        <main className="min-w-0 lg:pl-4">
          <Hero />
          <Problem />
          <History />
          <Pipeline />
          <DataMap />
          <Scoring />
          <Playground />
          <Glossary />
          <footer className="border-t border-rule py-12 text-sm text-ink-2">
            <p className="max-w-[70ch]">
              LexHack reports what published sources say. It is not legal advice. Statute text and judgments come from
              Kenya Law, through Internet Archive copies. The filings in the demo are made up; the court quotes are real
              and were checked by hand.
            </p>
            <p className="mt-3">
              Demo data is regenerated from the answer key with{' '}
              <span className="font-mono text-ink">uv run python edu/scripts/export_data.py</span>.
            </p>
          </footer>
        </main>
      </div>
    </>
  )
}
