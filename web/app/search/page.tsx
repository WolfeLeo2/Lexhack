import type { Metadata } from 'next'
import Link from 'next/link'
import { SearchBox } from '@/components/SearchBox'
import { SectionMeta } from '@/components/SectionMeta'
import { search } from '@/lib/api'
import { sectionHref, stripHead } from '@/lib/format'
import { snippet } from '@/lib/text'

export const metadata: Metadata = { title: 'Search' }

export default async function SearchPage({ searchParams }: PageProps<'/search'>) {
  const raw = (await searchParams).q
  const q = (Array.isArray(raw) ? raw[0] : raw ?? '').trim()
  const hits = q.length >= 2 ? await search(q) : []

  return (
    <div className="pt-10">
      <h1 className="sr-only">Search sections</h1>
      <div className="max-w-2xl">
        <SearchBox defaultValue={q} />
      </div>
      {q.length < 2 ? (
        <p className="mt-6 text-ink-2">Type at least two letters: a section’s subject, or words from its text.</p>
      ) : hits.length ? (
        <>
          <p className="mt-6 text-sm text-ink-2">Sections matching “{q}”, by wording and by meaning. Best match first.</p>
          <ol className="mt-3 divide-y divide-rule border-y border-rule">
            {hits.map((h) => (
              <li key={h.provision_id}>
                <Link href={sectionHref(h.provision_id)} className="block py-5 hover:bg-panel/60 sm:px-2">
                  <span className="flex flex-wrap items-baseline gap-x-3">
                    <span className="statute text-xl">
                      {h.act_title}, s.{h.number}
                    </span>
                    <span className="statute text-xl text-ink-2">{h.heading}</span>
                  </span>
                  <span className="statute mt-1 line-clamp-2 block max-w-[72ch] text-ink-2">
                    {snippet(stripHead(h.snippet, h.number, h.heading))}
                  </span>
                  <span className="mt-1.5 block">
                    <SectionMeta {...h} />
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </>
      ) : (
        <p className="mt-6 max-w-[62ch] text-ink-2">
          No section matches “{q}”. Search looks at the statute’s own wording, so try the legal term: “libel” rather
          than “defamation”, “defilement” rather than “sex with a child”.
        </p>
      )}
    </div>
  )
}
