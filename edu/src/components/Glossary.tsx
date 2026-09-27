import { Search } from 'lucide-react'
import { useState } from 'react'
import { GLOSSARY } from '../lib/data.ts'
import { play } from '../lib/feedback.ts'
import { Button, Part } from './ui.tsx'

const GROUPS = ['All', ...new Set(GLOSSARY.map((g) => g.group))]

function Marked({ text, q }: { text: string; q: string }) {
  const i = q ? text.toLowerCase().indexOf(q.toLowerCase()) : -1
  if (i < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, i)}
      <mark>{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  )
}

export function Glossary() {
  const [q, setQ] = useState('')
  const [group, setGroup] = useState('All')
  const items = GLOSSARY.filter(
    (g) => (group === 'All' || g.group === group) && `${g.term} ${g.def} ${g.eg ?? ''}`.toLowerCase().includes(q.toLowerCase()),
  )
  return (
    <Part id="glossary" n={7} title="Glossary" lede={<p>Every term this project uses, in plain words. Search, or filter by area.</p>}>
      <div className="flex flex-wrap items-center gap-3">
        <label className="relative w-full sm:w-72">
          <span className="sr-only">Search the glossary</span>
          <Search size={18} className="absolute top-1/2 left-3 -translate-y-1/2 text-ink-2" aria-hidden />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search terms"
            className="w-full rounded-md border border-rule bg-[#fbfcf9] py-2.5 pr-3 pl-10 placeholder:text-ink-2/60 focus:border-ink focus:outline-none"
          />
        </label>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by area">
          {GROUPS.map((g) => (
            <Button key={g} variant="ghost" aria-pressed={group === g} onClick={() => (setGroup(g), play('tick'))}>
              {g}
            </Button>
          ))}
        </div>
      </div>
      <p className="mt-4 text-sm text-ink-2">
        {items.length} of {GLOSSARY.length} terms
      </p>
      <dl className="mt-6 grid grid-cols-1 gap-x-12 gap-y-7 md:grid-cols-2">
        {items.map((g) => (
          <div key={g.term} className="border-t border-rule pt-4">
            <dt className="statute text-xl">
              <Marked text={g.term} q={q} />
              <span className="ml-3 font-sans text-sm text-ink-2">{g.group}</span>
            </dt>
            <dd className="mt-1.5">
              <Marked text={g.def} q={q} />
            </dd>
            {g.eg && (
              <dd className="mt-1.5 text-[0.95rem] text-ink-2">
                For example: <Marked text={g.eg} q={q} />
              </dd>
            )}
          </div>
        ))}
      </dl>
      {!items.length && <p className="mt-6 text-ink-2">No term matches "{q}". Try a shorter word, or choose All.</p>}
    </Part>
  )
}
