'use client'
import Link from 'next/link'
import { useState } from 'react'
import { StatusStamp } from './Stamp'

export interface Example {
  href: string
  tab: string
  act: string
  number: string
  heading: string
  text: string
  status: string
  quote: string
  court: string
  date: string
  caseName: string
}

/** A page of the Act as Kenya Law prints it, the status stamped on it, and the court's words pinned to it: the gap
 * Hakiki closes. Switching example replays the stamp and the pin. */
export function Specimen({ examples }: { examples: Example[] }) {
  const [i, setI] = useState(0)
  const x = examples[i]
  return (
    <div>
      <div role="tablist" aria-label="Examples" className="flex flex-wrap gap-2">
        {examples.map((e, j) => (
          <button
            key={e.href}
            type="button"
            role="tab"
            id={`ex-tab-${j}`}
            aria-selected={i === j}
            aria-controls="ex-panel"
            onClick={() => setI(j)}
            className="rounded-md border border-rule px-3 py-1.5 text-sm text-ink-2 transition-colors hover:border-ink-2 aria-selected:border-ink aria-selected:bg-ink aria-selected:text-paper"
          >
            {e.tab}
          </button>
        ))}
      </div>

      <div key={i} id="ex-panel" role="tabpanel" aria-labelledby={`ex-tab-${i}`} className="relative mt-5">
        <div className="relative rounded-sm bg-paper px-7 pt-6 pb-7 shadow-[0_1px_0_var(--color-rule),0_18px_40px_-26px_rgba(24,33,43,0.5)] ring-1 ring-rule">
          <p className="text-sm text-ink-2">Kenya Law’s published text</p>
          <p className="statute mt-3 text-[0.95rem] text-ink-2">
            {x.act}, section {x.number}
          </p>
          <p className="statute text-xl font-medium">{x.heading}</p>
          <p className="statute mt-2 line-clamp-4 text-[1.05rem] leading-relaxed">{x.text}</p>
          <div className="relative z-10 mt-5 flex justify-end">
            <StatusStamp status={x.status} />
          </div>
        </div>
        <Link
          href={x.href}
          className="pinned-note relative mt-5 mr-10 -ml-3 block rounded-sm bg-note px-6 pt-6 pb-5 shadow-[0_14px_30px_-18px_rgba(24,33,43,0.5)] ring-1 ring-note-rule transition-shadow hover:ring-ink-2 sm:mr-24"
        >
          <svg viewBox="0 0 24 24" className="absolute -top-3 left-8 h-6 w-6" aria-hidden>
            <circle cx="12" cy="10" r="6.5" fill="var(--color-seal)" />
            <circle cx="10" cy="8" r="2" fill="#fff" opacity=".35" />
            <path d="M12 16.5v6" stroke="var(--color-ink-2)" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          <p className="text-sm text-ink-2">
            What the {x.court} said, {x.date}
          </p>
          <blockquote className="court mt-2 line-clamp-4 text-[1.1rem]">“{x.quote}”</blockquote>
          <p className="mt-3 text-sm text-ink-2">
            {x.caseName}. <span className="text-gazette underline underline-offset-4">Open the section</span>
          </p>
        </Link>
      </div>
    </div>
  )
}
