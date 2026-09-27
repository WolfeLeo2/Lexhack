import { useRef, useState } from 'react'
import { play } from '../lib/feedback.ts'
import { FilingChecker } from './FilingChecker.tsx'
import { Lookup } from './Lookup.tsx'
import { Part } from './ui.tsx'

const TABS = [
  { id: 'lookup', label: 'Look up a section' },
  { id: 'check', label: 'Check a filing' },
] as const

export function Playground() {
  const [tab, setTab] = useState<'lookup' | 'check'>('lookup')
  const [focus, setFocus] = useState<string | null>(null)
  const top = useRef<HTMLDivElement>(null)

  return (
    <Part
      id="try"
      n={6}
      title="Try it"
      lede={
        <p>
          The API is built but not deployed yet, so this runs in your browser on a copy of its answers for 13
          sections, exported from the database and passed through the same status rules. By default you see only
          verified events, as the API does; switch on unverified leads to see what the pipeline found on its own. The
          live version will cover all 1,862 sections and 16,419 judgments.
        </p>
      }
    >
      <div ref={top} className="flex gap-1 border-b border-rule" role="tablist" aria-label="Demo">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => (setTab(t.id), play('turn'))}
            className="-mb-px border-b-2 border-transparent px-4 py-2.5 font-medium text-ink-2 aria-selected:border-ink aria-selected:text-ink"
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-8" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'lookup' ? (
          <Lookup focus={focus} />
        ) : (
          <FilingChecker
            onOpenSection={(pid) => {
              setFocus(pid)
              setTab('lookup')
              play('stamp')
              top.current?.scrollIntoView({ block: 'start' })
            }}
          />
        )}
      </div>
    </Part>
  )
}
