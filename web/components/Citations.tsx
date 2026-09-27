import { ExternalLink } from 'lucide-react'
import Link from 'next/link'
import type { CitingJudgment } from '@/lib/api'
import { fmtDate, shortCase } from '@/lib/format'
import { cleanUrl, tidySpaces } from '@/lib/text'

/** Judgments that cite the section without ruling on it: how the courts use it day to day. */
export function Citations({ total, judgments, more }: { total: number; judgments: CitingJudgment[]; more: string | null }) {
  return (
    <>
      <ol className="mt-6 max-w-[74ch] divide-y divide-rule border-y border-rule">
        {judgments.map((j) => {
          const url = cleanUrl(j.source_url)
          return (
            <li key={j.judgment_id} className="py-4">
              <p className="flex flex-wrap items-baseline gap-x-3">
                <span className="statute text-lg">{shortCase(j.title)}</span>
                <span className="text-sm text-ink-2">
                  {j.court}, {fmtDate(j.decision_date)}
                </span>
              </p>
              <p className="mt-1 text-[0.95rem] text-ink-2">
                <span className="court text-ink">“{tidySpaces(j.raw_text)}”</span>
                {j.paragraph && <>, para {j.paragraph}</>}
                {j.mentions > 1 && <>, and {j.mentions - 1} more {j.mentions === 2 ? 'mention' : 'mentions'}</>}.{' '}
                {url && (
                  <a href={url} className="link inline-flex items-center gap-1 whitespace-nowrap" target="_blank" rel="noreferrer">
                    Read it
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                    <span className="sr-only">(opens Kenya Law in a new tab)</span>
                  </a>
                )}
              </p>
            </li>
          )
        })}
      </ol>
      {more && judgments.length < total && (
        <Link href={more} scroll={false} className="mt-4 inline-block text-[0.95rem] text-ink-2 underline decoration-rule underline-offset-4 hover:text-ink">
          Show more citing judgments ({total - judgments.length} not shown)
        </Link>
      )}
    </>
  )
}
