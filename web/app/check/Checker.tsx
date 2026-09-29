'use client'
import Link from 'next/link'
import { useActionState, useEffect, useRef, useState } from 'react'
import { CheckedTag, UnverifiedTag } from '@/components/court'
import { BlankPage, KindIcon } from '@/components/illustrations'
import type { CaseCheck, Finding, QuoteCheck, SectionCheck } from '@/lib/api'
import { cap, courtActed, fmtDate, plural, sectionHref, shortCase } from '@/lib/format'
import { locator, splitAt, wordDiff } from '@/lib/text'
import { checkFiling, readFiling, type CheckState } from './actions'

const MAX = 200000
const EXHIBITS = [
  ['clean', 'Sound citations'],
  ['hallucinated', 'Invented and misquoted'],
  ['stale_law', 'Relies on struck-down law'],
] as const

/** A finding worth a second look: a case we can't match, words not found as quoted, or a section a court acted on. */
function needsLook(f: Finding) {
  if (f.case) return f.case.result !== 'found' || f.quotes.some((q) => q.result === 'close' || q.result === 'not_found')
  return !!f.section?.status && courtActed(f.section.status)
}

export function Checker() {
  const [state, action, pending] = useActionState<CheckState, FormData>(checkFiling, { text: '', report: null, error: null })
  const [text, setText] = useState('')
  const [exhibit, setExhibit] = useState<string | null>(null)
  const report = useRef<HTMLElement>(null)
  const picker = useRef<HTMLInputElement>(null)
  const [reading, setReading] = useState<string | null>(null) // file name while the server reads it
  const [readNote, setReadNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [dragging, setDragging] = useState(false)
  const [fed, setFed] = useState(0) // bumps to replay the feed-in animation when a file's text lands
  const [ocr, setOcr] = useState(false) // the text came from OCR of a scan: quote slips may be OCR's, not the author's

  async function readFile(file: File | undefined) {
    if (!file) return
    setReadNote(null)
    if (file.size > 4 * 1024 * 1024) return setReadNote({ ok: false, text: 'That file is larger than 4 MB. Paste the text instead.' })
    setReading(file.name)
    const form = new FormData()
    form.append('file', file)
    const r = await readFiling(form)
    setReading(null)
    if ('error' in r) return setReadNote({ ok: false, text: r.error })
    setText(r.text)
    setExhibit(null)
    setFed((n) => n + 1)
    setOcr(r.ocr_pages.length > 0)
    const what = r.kind === 'pdf' ? `${r.pages} ${r.pages === 1 ? 'page' : 'pages'}` : r.kind === 'docx' ? 'the document' : 'the text'
    const scanned = r.ocr_pages.length
      ? ` ${r.ocr_pages.length === r.pages ? 'It is a scan, read by OCR' : `Page${r.ocr_pages.length > 1 ? 's' : ''} ${r.ocr_pages.join(', ')} ${r.ocr_pages.length > 1 ? 'are scans' : 'is a scan'}, read by OCR`}: letters can be misread, so compare any flagged quote with the original.`
      : ''
    setReadNote({ ok: true, text: `Read ${what} from ${r.name}.${scanned} Check it reads right, then check the citations.` })
  }

  // The report arrives below the fold: bring it into view (gently, unless motion is reduced).
  useEffect(() => {
    if (!state.report) return
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    report.current?.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' })
  }, [state.report])

  async function loadExhibit(name: string) {
    setExhibit(name)
    setOcr(false)
    setText(await (await fetch(`/demo/${name}.txt`)).text())
  }

  return (
    <>
      <form action={action} className="mt-6">
        <div role="group" aria-label="Synthetic example filings" className="-mb-px flex items-end gap-1.5 overflow-x-auto pt-1 pl-3">
          {EXHIBITS.map(([name, label], k) => (
            <button
              key={name}
              type="button"
              aria-pressed={exhibit === name}
              onClick={() => loadExhibit(name)}
              className="exhibit-tab shrink-0 rounded-t-md border border-b-0 border-note-rule bg-note px-3.5 pt-1.5 pb-2 text-left aria-pressed:border-rule aria-pressed:bg-paper"
            >
              <span className="block text-xs text-ink-2">Exhibit {'ABC'[k]}</span>
              <span className="block text-[0.95rem]">{label}</span>
            </button>
          ))}
          <span className="shrink-0 pb-2 pl-2 text-sm text-ink-2">Synthetic examples, written by us</span>
          <button
            type="button"
            onClick={() => picker.current?.click()}
            disabled={!!reading}
            className="exhibit-tab group ml-auto flex shrink-0 items-center gap-2 rounded-t-md border border-b-0 border-rule bg-panel px-3.5 pt-1.5 pb-2 text-left disabled:opacity-60"
          >
            <svg viewBox="0 0 20 20" className="h-5 w-5 text-ink-2 transition-transform group-hover:-rotate-12" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M13.5 6.5 7.8 12.2a1.6 1.6 0 0 0 2.3 2.3l6-6a3.2 3.2 0 0 0-4.5-4.5l-6.2 6.2a4.8 4.8 0 0 0 6.8 6.8l4.2-4.2" />
            </svg>
            <span>
              <span className="block text-xs text-ink-2">Your filing</span>
              <span className="block text-[0.95rem]">Upload PDF or DOCX</span>
            </span>
          </button>
          <input
            ref={picker}
            type="file"
            accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(e) => {
              readFile(e.target.files?.[0])
              e.target.value = ''
            }}
          />
        </div>
        <div
          key={fed}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false)
          }}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            readFile(e.dataTransfer.files[0])
          }}
          className={`relative overflow-hidden rounded-sm bg-paper shadow-[0_1px_0_var(--color-rule),0_22px_44px_-30px_rgba(24,33,43,0.55)] ring-1 ring-rule ${pending || reading ? 'scan' : ''} ${fed ? 'feed-in' : ''}`}
        >
          {(dragging || reading) && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 border-2 border-dashed border-gazette bg-paper/85 text-ink-2" aria-live="polite">
              <svg viewBox="0 0 64 72" className={`h-16 w-16 ${dragging ? 'drop-hint' : ''}`} aria-hidden fill="none">
                <path d="M10 4h32l12 12v52H10z" fill="var(--color-paper)" stroke="var(--color-ink-2)" strokeWidth="1.5" />
                <path d="M42 4v12h12" stroke="var(--color-ink-2)" strokeWidth="1.5" />
                {[26, 34, 42, 50].map((y) => (
                  <line key={y} x1="18" x2="46" y1={y} y2={y} stroke="var(--color-rule)" strokeWidth="3" strokeLinecap="round" />
                ))}
              </svg>
              <span>{reading ? `Reading ${reading}…` : 'Drop the filing to read it'}</span>
            </div>
          )}
          <label htmlFor="filing" className="sr-only">
            Filing text
          </label>
          <textarea
            id="filing"
            name="text"
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              setExhibit(null)
            }}
            rows={14}
            placeholder="Paste a filing here, drop a PDF or DOCX on this page, or open one of the exhibits above."
            className="ruled statute block min-h-[24.5rem] w-full resize-y bg-transparent py-4 pr-5 pl-14 text-[1.02rem] placeholder:text-ink-2/70 focus:outline-none"
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <p className={`text-sm tabular-nums ${text.length > MAX ? 'text-seal' : 'text-ink-2'}`} aria-live="polite">
            {text.length > MAX ? `${(text.length - MAX).toLocaleString('en-GB')} characters over the ${MAX.toLocaleString('en-GB')} limit` : `${text.length.toLocaleString('en-GB')} characters`}
          </p>
          <button
            type="submit"
            disabled={pending}
            className="group inline-flex items-center gap-2.5 rounded-md bg-ink px-5 py-2.5 font-medium text-paper transition-[transform,background-color] hover:bg-gazette active:scale-[0.97] disabled:opacity-70"
          >
            <svg viewBox="0 0 20 20" className={`h-5 w-5 ${pending ? 'animate-spin' : 'transition-transform group-hover:-rotate-12'}`} aria-hidden fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <circle cx="8.5" cy="8.5" r="5.5" />
              <path d="M12.5 12.5 17 17" />
            </svg>
            {pending ? 'Reading the filing…' : 'Check citations'}
          </button>
        </div>
        {readNote && (
          <p className={`mt-3 ${readNote.ok ? 'text-gazette' : 'text-seal'}`} role={readNote.ok ? 'status' : 'alert'}>
            {readNote.text}
          </p>
        )}
        {state.error && (
          <p className="mt-3 text-seal" role="alert">
            {state.error}
          </p>
        )}
      </form>
      {state.report && (
        <Report key={state.text} ref={report} text={state.text} findings={state.report.findings} disclaimer={state.report.disclaimer} ocr={ocr} />
      )}
    </>
  )
}

function Report({
  ref,
  text,
  findings,
  disclaimer,
  ocr,
}: {
  ref: React.Ref<HTMLElement>
  text: string
  findings: Finding[]
  disclaimer: string
  ocr: boolean
}) {
  const [active, setActive] = useState<number | null>(null)
  const flagged = findings.filter(needsLook).length
  const cases = findings.filter((f) => f.kind === 'case').length
  const quotes = findings.reduce((n, f) => n + f.quotes.length, 0)

  if (!findings.length)
    return (
      <section ref={ref} className="mt-16 flex scroll-mt-24 flex-col items-start gap-6 border-t border-rule pt-10 sm:flex-row" aria-labelledby="report">
        <BlankPage className="w-20 shrink-0" />
        <div>
          <h2 id="report" className="statute text-2xl">
            No citations Hakiki can check
          </h2>
          <p className="mt-2 max-w-[64ch] text-ink-2">
            Hakiki reads neutral citations such as [2017] KESC 2 (KLR), eKLR citations such as [2017] eKLR, and sections of the Acts it holds. An empty report is not a
            sign the filing is sound.
          </p>
          <p className="mt-2 text-sm text-ink-2">{disclaimer}</p>
        </div>
      </section>
    )

  return (
    <section ref={ref} className="mt-16 scroll-mt-24 border-t border-rule pt-10" aria-labelledby="report">
      <h2 id="report" className="statute text-[2rem] leading-tight font-medium tracking-[-0.01em]">
        {flagged ? `${plural(flagged, 'citation')} worth a second look` : 'Nothing to flag in the citations we could read'}
      </h2>
      <p className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-ink-2">
        {(
          [
            ['case', cases, plural(cases, 'case')],
            ['section', findings.length - cases, plural(findings.length - cases, 'section')],
            ['quote', quotes, `${plural(quotes, 'quote')} compared`],
          ] as const
        )
          .filter(([, n]) => n > 0)
          .map(([kind, , label]) => (
            <span key={kind} className="inline-flex items-center gap-1.5">
              <KindIcon kind={kind} className="h-4 w-4" /> {label}
            </span>
          ))}
      </p>
      <p className="mt-1 text-sm text-ink-2">{disclaimer}</p>

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="lg:sticky lg:top-24 lg:self-start">
          <p className="mb-2 text-sm text-ink-2">The filing, marked up. Select a mark to read its note.</p>
          <div className="statute max-h-[72vh] overflow-y-auto rounded-sm bg-paper p-6 leading-relaxed whitespace-pre-wrap shadow-[0_1px_0_var(--color-rule),0_22px_44px_-30px_rgba(24,33,43,0.55)] ring-1 ring-rule">
            {splitAt(text, findings, (i, kept) => needsLook(findings[i]) && !needsLook(findings[kept])).map((p, i, parts) =>
              p.span === null ? (
                <span key={i}>{p.text}</span>
              ) : (
                <a
                  key={i}
                  href={`#f${p.span}`}
                  data-active={active === p.span}
                  onMouseEnter={() => setActive(p.span)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(p.span)}
                  onBlur={() => setActive(null)}
                  style={{ ['--i' as string]: parts.slice(0, i).filter((x) => x.span !== null).length }}
                  className={`mark-sweep ${needsLook(findings[p.span]) ? 'mark-flag' : ''}`}
                >
                  {p.text}
                </a>
              ),
            )}
          </div>
        </div>
        <ol className="space-y-4">
          {findings.map((f, i) => {
            const look = needsLook(f)
            return (
              <li
                key={i}
                id={`f${i}`}
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
                style={{ ['--i' as string]: i, ['--tilt' as string]: look ? `${i % 2 ? 0.5 : -0.5}deg` : '0deg' }}
                className={`note-in relative scroll-mt-28 rounded-sm px-5 pt-5 pb-4 transition-shadow ${
                  look ? 'bg-note shadow-[0_14px_30px_-20px_rgba(24,33,43,0.5)] ring-1 ring-note-rule' : 'ring-1 ring-rule'
                } ${active === i ? 'ring-2 ring-ink' : ''}`}
              >
                {look && (
                  <svg viewBox="0 0 24 24" className="absolute -top-3 left-6 h-6 w-6" aria-hidden>
                    <circle cx="12" cy="10" r="6.5" fill="var(--color-seal)" />
                    <circle cx="10" cy="8" r="2" fill="#fff" opacity=".35" />
                    <path d="M12 16.5v6" stroke="var(--color-ink-2)" strokeWidth="1.6" strokeLinecap="round" />
                  </svg>
                )}
                <p className="flex items-center gap-2 text-ink-2">
                  <KindIcon kind={f.kind} className="h-5 w-5 shrink-0" />
                  <span className="statute text-lg text-ink">{f.raw_text}</span>
                </p>
                {f.case && <CaseLine c={f.case} />}
                {f.quotes.map((q, j) => (
                  <QuoteLine key={j} q={q} unsettled={f.case?.result === 'possible_match'} ocr={ocr} />
                ))}
                {f.section && <SectionLine s={f.section} />}
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}

// What an eKLR match rests on (an eKLR citation carries only a year, so the report says how the case was found).
const BASIS: Partial<Record<NonNullable<CaseCheck['match_basis']>, string>> = {
  'case number': 'the case number',
  'party names and year': 'the parties’ names and the year',
  quote: 'the quoted words, found only in this judgment',
}

function CaseLine({ c }: { c: CaseCheck }) {
  const j = c.judgment
  if (c.result === 'possible_match')
    return (
      <div className="mt-2">
        <p className="text-ink-2">Possibly one of these cases in our collection. The citation gives only a year, and the names fit more than one:</p>
        <ul className="mt-3 grid gap-2.5 sm:grid-cols-2">
          {c.candidates.map((k, n) => (
            <li
              key={k.judgment_id}
              style={{ ['--i' as string]: n, ['--tilt' as string]: `${n % 2 ? 0.8 : -0.8}deg` }}
              className="candidate-card relative rounded-sm bg-paper px-3.5 pt-2.5 pb-2 shadow-[0_8px_18px_-14px_rgba(24,33,43,0.6)] ring-1 ring-rule"
            >
              <span aria-hidden className="absolute -top-2 right-3 rounded-full bg-note px-1.5 text-xs text-ink-2 ring-1 ring-note-rule">
                {n + 1}
              </span>
              {k.source_url ? (
                <a href={k.source_url} className="link" target="_blank" rel="noreferrer">
                  {shortCase(k.title)}
                </a>
              ) : (
                shortCase(k.title)
              )}
              <span className="block text-sm text-ink-2">
                {[k.neutral_citation, k.court, fmtDate(k.decision_date)].filter(Boolean).join(', ')}
              </span>
            </li>
          ))}
        </ul>
      </div>
    )
  if (c.result === 'not_in_collection')
    return (
      <p className="mt-2 text-ink-2">
        Not in our collection. We hold about 10% of published Kenyan judgments, so this does not show the case doesn’t exist. Look it up on Kenya Law.
      </p>
    )
  const name = j && `${shortCase(j.title)} ${j.neutral_citation ?? ''}`.trim()
  const title = j?.source_url ? (
    <a href={j.source_url} className="link" target="_blank" rel="noreferrer">
      {name}
    </a>
  ) : (
    name
  )
  if (c.result === 'name_mismatch')
    return (
      <p className="mt-2">
        <span className="text-seal">The filing calls this “{c.cited_name}”, but the citation belongs to a different case:</span> {title}.
      </p>
    )
  const basis = c.match_basis && BASIS[c.match_basis]
  return (
    <>
      <p className="mt-2 text-ink-2">In our collection: {title}.</p>
      {basis && (
        <p className="mt-1 inline-flex items-center gap-1.5 text-sm text-ink-2">
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M6.5 9.5 9.5 6.5M5 8 3.5 9.5a2.1 2.1 0 0 0 3 3L8 11M8 5l1.5-1.5a2.1 2.1 0 0 1 3 3L11 8" />
          </svg>
          Matched on {basis}
        </p>
      )}
    </>
  )
}

// Below this, the "nearest passage" shares a few words by chance and marking the quote against it is noise.
const COMPARABLE = 0.6

const QUOTE_LABEL: Record<QuoteCheck['result'], string> = {
  verbatim: 'The quoted words are in the judgment, word for word',
  close: 'The quote is close to the judgment, but not word for word',
  not_found: 'The quoted words are not in the judgment',
  not_checked: 'Quote not checked: we don’t hold this judgment’s text',
}

function QuoteLine({ q, unsettled = false, ocr = false }: { q: QuoteCheck; unsettled?: boolean; ocr?: boolean }) {
  const marked = (q.result === 'close' || (q.result === 'not_found' && (q.similarity ?? 0) >= COMPARABLE)) && q.court_text
  return (
    <div className="mt-4 border-l-2 border-rule pl-4">
      <p className={`flex items-start gap-1.5 ${q.result === 'close' || q.result === 'not_found' ? 'text-seal' : 'text-ink-2'}`}>
        <KindIcon kind="quote" className="mt-1 h-4 w-4 shrink-0" />
        <span>
          {unsettled && q.result === 'not_checked'
            ? 'Quote not checked: the citation fits more than one case, and the words were not found in just one of them'
            : QUOTE_LABEL[q.result]}
          {q.result === 'close' && q.similarity !== null && ` (${Math.round(q.similarity * 100)}% the same)`}
          {q.paragraph && `, paragraph ${q.paragraph}`}.
          {ocr && (q.result === 'close' || q.result === 'not_found') && ' The filing was read by OCR, so this may be an OCR slip.'}
          {q.judgment_ocr && (q.result === 'close' || q.result === 'not_found') && ' Our copy of this judgment was read by OCR from a scan, so the difference may be a slip in our text.'}
        </span>
      </p>
      {marked ? (
        <>
          <p className="mt-2 text-sm text-ink-2">{q.result === 'close' ? 'The filing’s quote, marked against what the court wrote:' : 'The filing’s quote, marked against the nearest passage in the judgment:'}</p>
          <blockquote className="court mt-1 text-[1.05rem]">
            “
            {wordDiff(q.quote, q.court_text!).map((d, k) =>
              d.op === 'same' ? (
                <span key={k}>{d.word} </span>
              ) : d.op === 'del' ? (
                <del key={k} className="text-seal decoration-seal/70 decoration-2">
                  {d.word}{' '}
                </del>
              ) : (
                <ins key={k} className="hl no-underline">
                  {d.word}{' '}
                </ins>
              ),
            )}
            ”
          </blockquote>
          <p className="mt-1.5 text-xs text-ink-2">
            <del className="text-seal decoration-seal/70">Struck</del>: in the filing, not the judgment. <ins className="hl no-underline">Highlighted</ins>: the judgment’s words
            the filing left out.
          </p>
        </>
      ) : (
        <blockquote className="court mt-2 text-ink-2">“{q.quote}”</blockquote>
      )}
    </div>
  )
}

function SectionLine({ s }: { s: SectionCheck }) {
  if (s.result === 'not_covered' || !s.provision)
    return <p className="mt-2 text-ink-2">{s.act_ref ? `${s.act_ref}: not` : 'Not'} a section Hakiki covers yet.</p>
  const p = s.provision
  const acted = !!s.status && courtActed(s.status)
  return (
    <div className="mt-2">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Link href={sectionHref(p.provision_id)} className="link">
          {p.act_title}, s.{p.number}
        </Link>
        <span className={`stamp inline-block rounded-[3px] border-2 px-2 py-0.5 text-sm font-medium ${acted ? 'border-seal text-seal' : 'border-ink-2/50 text-ink-2'}`}>
          {cap(s.status ?? '')}
        </span>
      </p>
      {s.summary_events.map((e) => (
        <blockquote key={e.event_id} className="mt-3 border-l-2 border-seal/60 pl-4">
          <p className="court">“{e.operative_quote}”</p>
          <footer className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-2">
            {e.source_url ? (
              <a href={e.source_url} className="link" target="_blank" rel="noreferrer">
                {shortCase(e.title)} {e.neutral_citation}
              </a>
            ) : (
              <span>{shortCase(e.title)}</span>
            )}
            {e.source_paragraph && <span>{locator(e.source_paragraph)}</span>}
            {e.verified ? <CheckedTag by={e.verified_by} /> : <UnverifiedTag />}
          </footer>
        </blockquote>
      ))}
    </div>
  )
}
