import { fmtDate } from '@/lib/format'

/** Every archived version of an Act on one line of years, so gaps in the archive are visible at a glance. */
export function VersionRail({ versions }: { versions: string[] }) {
  const yf = (d: string) => {
    const dt = new Date(d + 'T00:00:00')
    return dt.getFullYear() + dt.getMonth() / 12
  }
  const lo = Math.floor(yf(versions[0]))
  const hi = Math.max(lo + 1, Math.ceil(yf(versions.at(-1)!) + 0.01))
  const pct = (d: string) => ((yf(d) - lo) / (hi - lo)) * 100
  return (
    <figure>
      <figcaption className="text-[0.95rem] text-ink-2">
        {versions.length === 1
          ? `One version archived, ${fmtDate(versions[0])}.`
          : `${versions.length} versions archived, ${fmtDate(versions[0])} to ${fmtDate(versions.at(-1)!)}. The latest is shown on each section.`}
      </figcaption>
      <div className="relative mx-2 mt-8 mb-6 h-px bg-ink-2/50" role="list" aria-label="Archived versions">
        {versions.map((v, i) => (
          <span
            key={v}
            role="listitem"
            className="group absolute top-0 -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${pct(v)}%` }}
            title={fmtDate(v)}
          >
            <span className={`block h-3 w-3 rotate-45 border-2 ${i === versions.length - 1 ? 'border-seal bg-seal' : 'border-ink bg-paper'}`} />
            <span className="sr-only">{fmtDate(v)}</span>
          </span>
        ))}
        <span className="absolute top-3 left-0 -translate-x-1/2 text-xs text-ink-2 tabular-nums">{lo}</span>
        <span className="absolute top-3 right-0 translate-x-1/2 text-xs text-ink-2 tabular-nums">{hi}</span>
      </div>
    </figure>
  )
}
