'use client'
import Link from 'next/link'
import { useDeferredValue, useState } from 'react'
import type { ActSection } from '@/lib/api'
import { courtActed, sectionHref } from '@/lib/format'
import { SectionMeta } from './SectionMeta'

/** An Act's table of contents, filterable by number or heading. Sections a court has acted on carry their status. */
export function SectionList({ sections }: { sections: ActSection[] }) {
  const [q, setQ] = useState('')
  const [only, setOnly] = useState<'all' | 'rulings' | 'leads'>('all')
  const dq = useDeferredValue(q.trim().toLowerCase().replace(/^s(ection)?\.?\s*/, ''))
  const acted = sections.filter((s) => courtActed(s.status)).length
  const withLeads = sections.filter((s) => s.lead_count > 0).length
  const shown = sections.filter(
    (s) =>
      (only === 'all' || (only === 'rulings' ? courtActed(s.status) : s.lead_count > 0)) &&
      (!dq || s.number?.toLowerCase() === dq || (s.heading ?? '').toLowerCase().includes(dq)),
  )

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <label className="relative w-full max-w-sm">
          <span className="sr-only">Filter sections</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter by number or heading, e.g. 204"
            className="w-full rounded-md border border-rule bg-paper/80 px-3 py-2 placeholder:text-ink-2/70 focus:border-ink focus:outline-none"
          />
        </label>
        <fieldset className="flex flex-wrap gap-x-5 gap-y-2 text-[0.95rem] text-ink-2">
          <legend className="sr-only">Show</legend>
          {(
            [
              ['all', `All sections (${sections.length})`],
              ['rulings', `Checked court rulings (${acted})`],
              ['leads', `Unverified leads (${withLeads})`],
            ] as const
          ).map(([v, label]) => (
            <label key={v} className="flex cursor-pointer items-center gap-2">
              <input
                type="radio"
                name="only"
                checked={only === v}
                onChange={() => setOnly(v)}
                className="h-4 w-4 accent-[var(--color-seal)]"
              />
              {label}
            </label>
          ))}
        </fieldset>
      </div>

      <p className="mt-6 text-sm text-ink-2" aria-live="polite">
        {shown.length === sections.length ? `${sections.length} sections` : `${shown.length} of ${sections.length} sections`}
      </p>
      {shown.length ? (
        <ol className="mt-2 divide-y divide-rule border-y border-rule">
          {shown.map((s) => {
            const a = courtActed(s.status)
            return (
              <li key={s.provision_id}>
                <Link
                  href={sectionHref(s.provision_id)}
                  className="grid grid-cols-[4rem_minmax(0,1fr)] items-baseline gap-x-4 py-2.5 hover:bg-panel/60 sm:grid-cols-[4rem_minmax(0,1fr)_18rem]"
                >
                  <span className={`statute text-right text-lg tabular-nums ${a ? 'text-seal' : 'text-ink-2'}`}>{s.number}</span>
                  <span className="statute text-[1.1rem]">{s.heading ?? 'Untitled section'}</span>
                  <span className="col-start-2 text-sm sm:col-start-3">
                    <SectionMeta {...s} />
                  </span>
                </Link>
              </li>
            )
          })}
        </ol>
      ) : (
        <p className="mt-4 text-ink-2">No section matches “{q}”. Try a section number, or a word from its heading.</p>
      )}
    </div>
  )
}
