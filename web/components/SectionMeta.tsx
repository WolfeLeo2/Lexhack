import type { Counts } from '@/lib/api'
import { cap, courtActed, plural } from '@/lib/format'

/** The line under a section in any list. A court's ruling leads; otherwise how often judgments cite it, so a list of
 * untouched sections doesn't read as one status repeated four hundred times. */
export function SectionMeta({ status, cited_by, lead_count }: Counts & { status: string }) {
  const acted = courtActed(status)
  return (
    <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[0.95rem]">
      {acted ? (
        <span className="text-seal">{cap(status)}</span>
      ) : status === 'repealed' ? (
        <span className="text-ink-2">Repealed by Parliament</span>
      ) : (
        <span className="text-ink-2">{cited_by ? `Cited in ${plural(cited_by, 'judgment')}` : 'Not cited in the judgments we hold'}</span>
      )}
      {lead_count > 0 && (
        <span className="rounded-sm border border-dashed border-ink-2/60 px-1.5 text-xs text-ink-2" title="Possible rulings found by the pipeline, not yet checked by a person">
          {plural(lead_count, 'unverified lead')}
        </span>
      )}
    </span>
  )
}
