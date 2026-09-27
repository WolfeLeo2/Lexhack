import { AlertTriangle, Check, CircleHelp, Pencil, RotateCcw, ScanSearch } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { type CaseFinding, type Finding, type SectionFinding, check } from '../lib/checker.ts'
import { FILINGS, JUDGMENTS, PROVISIONS, eventById } from '../lib/data.ts'
import { play } from '../lib/feedback.ts'
import { Button, CourtWords, EVENT_LABEL, fmtDate, shortCase, year } from './ui.tsx'

type Level = 'ok' | 'note' | 'flag'

function level(f: Finding): Level {
  if (f.kind === 'section') {
    if (!f.result) return 'note'
    if (/limited|unconstitutional|repealed/.test(f.result.status)) return 'flag'
    return f.result.status.includes('no recorded') ? 'ok' : 'note'
  }
  if (!f.judgment || (f.quote && !f.quote.verbatim) || f.rulings.some((r) => r.event.state !== 'in effect')) return 'flag'
  return 'ok'
}

const ICON = {
  ok: <Check size={16} aria-label="Nothing to flag" className="text-gazette" />,
  note: <CircleHelp size={16} aria-label="Worth a look" className="text-ink-2" />,
  flag: <AlertTriangle size={16} aria-label="Flagged" className="text-seal" />,
}

export function FilingChecker({ onOpenSection }: { onOpenSection: (pid: string) => void }) {
  const [fid, setFid] = useState(FILINGS[0].id)
  const [text, setText] = useState(FILINGS[0].text)
  const [editing, setEditing] = useState(false)
  const [results, setResults] = useState<Finding[] | null>(null)
  const [shown, setShown] = useState(0)
  const [active, setActive] = useState<number | null>(null)
  const reduce = useReducedMotion()
  const cards = useRef<(HTMLLIElement | null)[]>([])
  const filing = FILINGS.find((f) => f.id === fid)!

  const choose = (id: string) => {
    const f = FILINGS.find((x) => x.id === id)!
    setFid(id)
    setText(f.text)
    setEditing(false)
    setResults(null)
    play('tick')
  }

  const run = () => {
    setEditing(false)
    setResults(check(text, PROVISIONS, JUDGMENTS))
    setShown(0)
    setActive(null)
  }

  // reveal results one by one, with a sound per result
  useEffect(() => {
    if (!results || shown >= results.length) return
    const t = setTimeout(() => {
      play(level(results[shown]) === 'flag' ? 'flag' : 'tick')
      setShown((n) => n + 1)
    }, reduce ? 0 : 320)
    return () => clearTimeout(t)
  }, [results, shown, reduce])

  const flags = results?.filter((f) => level(f) === 'flag').length ?? 0

  return (
    <div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3" role="radiogroup" aria-label="Choose a demo filing">
        {FILINGS.map((f) => (
          <button
            key={f.id}
            type="button"
            role="radio"
            aria-checked={fid === f.id}
            onClick={() => choose(f.id)}
            className="rounded-md border border-rule p-4 text-left transition-colors hover:border-ink-2 aria-checked:border-ink aria-checked:bg-[#fbfcf9]"
          >
            <span className="block font-medium">{f.title}</span>
            <span className="mt-1 block text-sm text-ink-2">{f.about}</span>
          </button>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div>
          <div className="relative rounded-md border border-rule bg-[#fbfcf9]">
            <span className="absolute top-3 right-3 rounded-sm border border-ink-2/40 px-1.5 text-xs text-ink-2">
              Synthetic filing, written for this demo
            </span>
            {editing ? (
              <textarea
                value={text}
                onChange={(e) => (setText(e.target.value), setResults(null))}
                aria-label="Filing text"
                className="statute block min-h-[26rem] w-full resize-y rounded-md bg-transparent p-6 pt-12 text-[1.02rem] focus:outline-none"
              />
            ) : (
              <FilingText text={text} results={results?.slice(0, shown) ?? []} active={active} onPick={(i) => {
                setActive(i)
                cards.current[i]?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'nearest' })
              }} />
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button onClick={run}>
              <ScanSearch size={18} aria-hidden /> Check citations
            </Button>
            <Button variant="ghost" onClick={() => (setEditing(!editing), play('tick'))} aria-pressed={editing}>
              <Pencil size={16} aria-hidden /> {editing ? 'Done editing' : 'Edit the text'}
            </Button>
            {text !== filing.text && (
              <Button variant="ghost" onClick={() => choose(fid)}>
                <RotateCcw size={16} aria-hidden /> Reset
              </Button>
            )}
          </div>
          <p className="mt-3 text-sm text-ink-2">
            Try your own: edit the text and cite, say, "section 132 of the Penal Code" or "Republic v Mwangi [2024] KESC
            34", then check again.
          </p>
        </div>

        <div aria-live="polite">
          {!results && (
            <div className="rounded-md border border-dashed border-rule p-6 text-ink-2">
              <p className="font-medium text-ink">Three checks for every citation</p>
              <ol className="mt-2 list-decimal space-y-1 pl-5">
                <li>Does the cited case exist?</li>
                <li>Is the quoted passage really in it?</li>
                <li>Is the cited section, or the cited ruling, still good law?</li>
              </ol>
              <p className="mt-3">
                It deliberately doesn't judge whether a case supports the argument. That's a research problem for later.
              </p>
            </div>
          )}
          {results && (
            <>
              <p className="statute text-2xl">
                {results.length === 0
                  ? 'No citations found.'
                  : `${results.length} citation${results.length > 1 ? 's' : ''}, ${flags} flagged`}
              </p>
              <ol className="mt-4 space-y-3">
                {results.slice(0, shown).map((f, i) => (
                  <motion.li
                    key={`${f.start}-${f.kind}`}
                    ref={(el) => {
                      cards.current[i] = el
                    }}
                    initial={{ opacity: 0, y: reduce ? 0 : 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    onMouseEnter={() => setActive(i)}
                    className={`rounded-md border bg-[#fbfcf9] p-4 transition-colors ${
                      active === i ? 'border-ink' : 'border-rule'
                    } ${level(f) === 'flag' ? 'border-l-4 border-l-seal' : ''}`}
                  >
                    <div className="flex items-start gap-2">
                      <span className="grid grid-cols-1 h-5 w-5 shrink-0 place-items-center rounded-full bg-ink text-[0.7rem] text-paper">{i + 1}</span>
                      <div className="min-w-0 flex-1">
                        {f.kind === 'section' ? <SectionResult f={f} onOpen={onOpenSection} /> : <CaseResult f={f} />}
                      </div>
                      {ICON[level(f)]}
                    </div>
                  </motion.li>
                ))}
              </ol>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function FilingText({ text, results, active, onPick }: { text: string; results: Finding[]; active: number | null; onPick: (i: number) => void }) {
  const spans = useMemo(() => {
    const all = results.flatMap((f, i) => [
      { start: f.start, end: f.end, i, quote: false },
      ...(f.kind === 'case' && f.quote ? [{ start: f.quote.start, end: f.quote.end, i, quote: true }] : []),
    ])
    all.sort((a, b) => a.start - b.start)
    const keep: typeof all = []
    for (const s of all) if (!keep.length || s.start >= keep[keep.length - 1].end) keep.push(s)
    return keep
  }, [results])
  const parts = []
  let at = 0
  for (const s of spans) {
    if (s.start > at) parts.push(<span key={`t${at}`}>{text.slice(at, s.start)}</span>)
    const f = results[s.i]
    const lv = level(f)
    parts.push(
      <span
        key={`s${s.start}`}
        role="button"
        tabIndex={0}
        onClick={() => onPick(s.i)}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onPick(s.i))}
        className={`cursor-pointer rounded-[2px] transition-colors [box-decoration-break:clone] ${
          s.quote ? 'underline decoration-dotted underline-offset-4' : lv === 'flag' ? 'bg-seal/12 text-seal' : 'bg-mark/60'
        } ${active === s.i ? 'outline outline-2 outline-ink' : ''}`}
      >
        {text.slice(s.start, s.end)}
        {!s.quote && <sup className="ml-0.5 font-sans text-[0.65rem] text-ink-2">{s.i + 1}</sup>}
      </span>,
    )
    at = s.end
  }
  parts.push(<span key="end">{text.slice(at)}</span>)
  return <div className="statute p-6 pt-12 text-[1.02rem] whitespace-pre-wrap">{parts}</div>
}

function SectionResult({ f, onOpen }: { f: SectionFinding; onOpen: (pid: string) => void }) {
  const label = `${f.actName} s.${f.number}${f.subsection}`
  if (!f.result)
    return (
      <>
        <p className="font-medium">{label}</p>
        <p className="mt-1 text-[0.95rem] text-ink-2">
          {f.actId
            ? 'We hold this Act, but this demo only carries 13 sections. The live version would look it up.'
            : 'Not one of the 8 Acts we hold yet, so its status can\'t be checked.'}
        </p>
      </>
    )
  const r = f.result
  const [top] = r.summary_events
  return (
    <>
      <p className="font-medium">
        {label}: <span className={level(f) === 'flag' ? 'text-seal' : ''}>{r.status}</span>
      </p>
      {top && (
        <>
          <p className="mt-1 text-sm text-ink-2">
            {EVENT_LABEL[top.event_type]}
            {top.scope === 'partial' ? ' in part' : ''} by the {top.court}, {fmtDate(top.effective_date)}, in {shortCase(top)}:
          </p>
          <CourtWords quote={top.operative_quote} mark={top.scope_text} className="mt-1 line-clamp-4 text-[0.98rem]" />
        </>
      )}
      <button type="button" className="mt-2 text-sm font-medium text-gazette underline underline-offset-2" onClick={() => onOpen(r.provision.provision_id)}>
        Open s.{f.number} in the lookup
      </button>
    </>
  )
}

function CaseResult({ f }: { f: CaseFinding }) {
  const j = f.judgment
  return (
    <>
      <p className="font-medium">{f.raw.trim()}</p>
      <dl className="mt-2 space-y-2 text-[0.95rem]">
        <div>
          <dt className="inline font-medium">Exists? </dt>
          <dd className="inline text-ink-2">
            {j ? (
              <>
                Yes: {j.court}, {fmtDate(j.decision_date)}, {j.neutral_citation}.{' '}
                <a className="link" href={j.source_url} target="_blank" rel="noreferrer">
                  Kenya Law
                </a>
              </>
            ) : (
              <span className="text-seal">
                Not found. The real index holds 16,419 judgments (this demo holds {JUDGMENTS.length}), about a tenth of
                all Kenyan judgments, so "not found" means check it by hand before relying on it. It is not proof the
                case is fake.
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="inline font-medium">Quote? </dt>
          <dd className="inline text-ink-2">
            {!f.quote && 'No quotation given.'}
            {f.quote?.verbatim && 'Found word for word in the judgment.'}
            {f.quote && !f.quote.verbatim && (
              <span className="text-seal">
                {f.quote.closest ? 'Not what the judgment says. Closest passage:' : j ? 'Not in any passage we hold from this judgment.' : "Can't be checked without the judgment."}
              </span>
            )}
          </dd>
          {f.quote?.closest && (
            <p className="court mt-1.5 rounded-sm bg-panel p-2.5 text-[0.95rem]">
              {f.quote.diff.map((t, k) => (
                <span key={k}>
                  {t.kind === 'same' && t.w}
                  {t.kind === 'missing' && <ins className="bg-mark/70 no-underline">{t.w}</ins>}
                  {t.kind === 'added' && <del className="text-seal decoration-seal">{t.w}</del>}{' '}
                </span>
              ))}
              <span className="mt-1 block font-sans text-xs text-ink-2 not-italic">
                Highlighted: the judgment's words. Struck through: words the filing added.
              </span>
            </p>
          )}
        </div>
        {j && (
          <div>
            <dt className="inline font-medium">Still stands? </dt>
            <dd className="inline text-ink-2">
              {!f.rulings.length && 'It made no ruling on a section we track.'}
              {f.rulings.map(({ provision: p, event: e }) => {
                const by = eventById(e.superseded_by)
                return (
                  <span key={e.event_id} className={`block ${e.state !== 'in effect' ? 'text-seal' : ''}`}>
                    Its ruling on {p.act_title} s.{p.number} ({EVENT_LABEL[e.event_type].toLowerCase()}){' '}
                    {e.state === 'in effect' ? 'still counts.' : `was ${e.state}`}
                    {by && ` by ${shortCase(by)} (${by.court}, ${year(by.effective_date)}).`}
                  </span>
                )
              })}
            </dd>
          </div>
        )}
      </dl>
    </>
  )
}
