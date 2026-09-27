import { structure } from '@/lib/text'

const INDENT = ['pl-0', 'pl-0', 'pl-8', 'pl-16']

/** A section's text laid out as the printed Act is: one subsection per line, paragraphs indented under it, the
 * reviser's amendment notes set apart underneath. */
export function StatuteText({ text, number }: { text: string; number: string | null }) {
  const { clauses, notes } = structure(text)
  // a list never skips a level on screen, even when the Act goes straight from (1) to (i)
  const levels: number[] = []
  for (const c of clauses) levels.push(c.level === 0 ? 0 : Math.min(c.level, (levels.at(-1) ?? 0) + 1))
  return (
    <div className="mt-8 rounded-sm bg-panel/70 py-6 pr-6 pl-5 shadow-[inset_3px_0_0_var(--color-rule)]">
      <div className="flex gap-4">
        <span className="statute pt-[0.2rem] text-[1.3rem] text-ink-2/70 tabular-nums" aria-hidden>
          {number}.
        </span>
        {clauses.length ? (
          <div className="statute min-w-0 space-y-2 text-[1.25rem] leading-[1.6]">
            {clauses.map((c, i) => (
              <p key={i} className={`${INDENT[levels[i]]} ${c.label ? 'grid grid-cols-[2.6rem_minmax(0,1fr)]' : ''}`}>
                {c.label && <span className="text-ink-2">{c.label}</span>}
                <span>{c.text}</span>
              </p>
            ))}
          </div>
        ) : (
          <p className="text-ink-2">This version has no text for the section beyond its heading.</p>
        )}
      </div>
      {notes.length > 0 && (
        <div className="mt-5 border-t border-rule pt-3 pl-[3.1rem] text-sm text-ink-2">
          <p>Amendment notes in the published text:</p>
          <ul className="mt-1 space-y-0.5">
            {notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
