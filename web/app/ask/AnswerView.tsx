'use client'
// One question and its answer: the steps, the streamed text, then the answer or draft as parts (rulings quoted from the
// database, never by the model), with Copy / Word / PDF.
import { BookOpen, Check, CircleAlert, ClipboardCheck, Copy, FileDown, FileSearch, FileText, Gavel, Library, LoaderCircle, type LucideIcon, PenLine, RotateCcw, ScrollText, Search, Sparkles } from 'lucide-react'
import Link from 'next/link'
import { Fragment, type ReactNode, useEffect, useState } from 'react'
import { CourtWords } from '@/components/court'
import { type Answer, type CaseRef, type CheckFlag, type Inline, isBlank, type Part, type Ruling as RulingPart, type SectionRef, type Step, toLines } from '@/lib/answer'
import { cap, courtActed, sectionHref, shortCase } from '@/lib/format'
import { cleanUrl, locator } from '@/lib/text'
import type { Turn } from './useChats'

const ICONS: Record<string, LucideIcon> = {
  find_section: BookOpen,
  search_sections: Search,
  get_section: ScrollText,
  find_case: Gavel,
  citing_judgments: Library,
  list_acts: Library,
  check_text: FileSearch,
  check: ClipboardCheck,
  revise: PenLine,
}

/** onRetry only on the last turn: asking again replaces it, and an earlier one would drop the turns after it. */
export function TurnView({ t, onRetry }: { t: Turn; onRetry?: () => void }) {
  return (
    <article>
      <div className="relative ml-auto w-fit max-w-[60ch]">
        <p className="statute rounded-md bg-panel px-4 py-2.5 text-lg break-words">{t.question}</p>
        <svg aria-hidden="true" viewBox="0 0 16 14" className="pointer-events-none absolute top-[calc(100%-1px)] right-6 h-3.5 w-4 text-panel">
          <path d="M0 0h16v14z" fill="currentColor" />
        </svg>
      </div>
      <div aria-live="polite" className="mt-5">
        {(t.pending || t.steps.length > 0) && <Steps steps={t.steps} pending={t.pending && !t.answer && !t.live.length} />}
        {!t.answer && !t.error && t.live.length > 0 && <Writing chunks={t.live} draft={t.mode === 'draft'} />}
        {t.answer && t.answer.label !== undefined && <Draft a={t.answer} question={t.question} />}
        {t.answer && t.answer.label === undefined && (
          <div className="answer-in mt-5 max-w-[68ch]">
            <div className="space-y-4">
              <AnswerBody parts={t.answer.parts} />
            </div>
            <Actions a={t.answer} question={t.question} />
          </div>
        )}
        {t.error && (
          <p className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-note-rule bg-note px-4 py-3" role="alert">
            <span>{t.error}</span>
            {onRetry && (
              <button type="button" onClick={onRetry} className="link inline-flex items-center gap-1.5 text-gazette underline underline-offset-[3px]">
                <RotateCcw className="h-4 w-4" aria-hidden />
                Ask again
              </button>
            )}
          </p>
        )}
      </div>
    </article>
  )
}

/** The answer as plain text for pasting: a draft's label first; no "[status: …]" or "<url>" markers. */
function plainText(a: Answer) {
  const body = a.text.replace(/ ?\[status: [^\]]*\]/g, '').replace(/ ?<https?:[^>\s]*>/g, '')
  return a.label ? `${a.label}\n\n${body}` : body
}

type Busy = { what: 'copy' | 'docx' | 'pdf'; state: 'busy' | 'done' | 'failed'; message?: string }

/** Copy, Download Word, Download PDF: quiet, under the answer. The files are built by the API from the database. */
function Actions({ a, question }: { a: Answer; question: string }) {
  const [busy, setBusy] = useState<Busy | null>(null)
  useEffect(() => {
    if (!busy || busy.state === 'busy') return
    const id = setTimeout(() => setBusy(null), busy.state === 'failed' ? 6000 : 2000)
    return () => clearTimeout(id)
  }, [busy])

  const copy = () => {
    const p = navigator.clipboard?.writeText(plainText(a))
    if (!p) return setBusy({ what: 'copy', state: 'failed', message: 'Couldn’t copy' })
    p.then(() => setBusy({ what: 'copy', state: 'done' }), () => setBusy({ what: 'copy', state: 'failed', message: 'Couldn’t copy' }))
  }
  const download = async (format: 'docx' | 'pdf') => {
    setBusy({ what: format, state: 'busy' })
    try {
      const res = await fetch('/ask/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format, question, mode: a.label !== undefined ? 'draft' : 'answer', parts: a.parts, check: a.check, label: a.label }),
      })
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.error ?? 'Couldn’t make the file. Try again in a moment.')
      const name = res.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] ?? `hakiki.${format}`
      const url = URL.createObjectURL(await res.blob())
      const link = Object.assign(document.createElement('a'), { href: url, download: name })
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 10_000)
      setBusy({ what: format, state: 'done' })
    } catch (err) {
      setBusy({ what: format, state: 'failed', message: err instanceof TypeError ? 'The connection dropped. Try again.' : (err as Error).message })
    }
  }

  const button = (what: Busy['what'], Icon: LucideIcon, label: string, onClick: () => void) => {
    const mine = busy?.what === what ? busy.state : null
    const Shown = mine === 'busy' ? LoaderCircle : mine === 'done' ? Check : Icon
    return (
      <button
        type="button"
        onClick={onClick}
        disabled={busy?.state === 'busy'}
        className="link inline-flex items-center gap-1.5 rounded-sm px-1.5 py-1 text-sm text-ink-2 hover:text-ink disabled:opacity-60"
      >
        <Shown className={`h-4 w-4 ${mine === 'busy' ? 'motion-safe:animate-spin' : ''}`} aria-hidden />
        {what === 'copy' && mine === 'done' ? 'Copied' : label}
      </button>
    )
  }
  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-1 gap-y-1 border-t border-rule pt-2">
      {button('copy', Copy, 'Copy text', copy)}
      {button('docx', FileText, 'Download Word', () => download('docx'))}
      {button('pdf', FileDown, 'Download PDF', () => download('pdf'))}
      <span className="px-1.5 text-sm text-ink-2" role="status">
        {busy?.state === 'busy' ? 'Building the file from Hakiki’s records…' : busy?.state === 'failed' ? busy.message : ''}
      </span>
    </div>
  )
}

// Results with fixed words, in the /check page's language; the rest (sections, notes, not_checked, not_confirmed) show
// the server's note, which says what the check found. No verdict colours: flagged vs checked is in words and icon.
const CHECK_WORDS: Record<string, string> = {
  found: 'Verified: in Hakiki’s collection',
  verbatim: 'Quote matches the judgment, word for word',
  not_in_collection: 'Not in Hakiki’s collection — check before relying on it',
  possible_match: 'Could be more than one case in Hakiki’s collection — check which one is meant',
  name_mismatch: 'The citation belongs to a different case in Hakiki’s collection',
  close: 'The quote is close to the judgment, but not word for word',
  not_found: 'The quoted words are not in the judgment',
}
const KIND_WORDS: Record<CheckFlag['kind'], string> = { case: 'Case', quote: 'Quote', section: 'Section', note: 'Note' }

/** A draft: the label, the draft on a sheet of paper, Copy / Word / PDF, then everything Hakiki checked. */
function Draft({ a, question }: { a: Answer; question: string }) {
  const check = a.check ?? []
  const anyFlagged = check.some((f) => f.flagged)
  return (
    <div className="answer-in mt-5 max-w-[72ch]">
      <p className="text-sm text-ink-2">{a.label}</p>
      <div className="draft-paper relative mt-3 rounded-sm bg-paper px-6 pt-5 pb-3 shadow-[0_14px_30px_-22px_rgba(24,33,43,0.7)] ring-1 ring-rule sm:px-8">
        <div className="statute space-y-4 text-[1.05rem] leading-relaxed">
          <AnswerBody parts={a.parts} />
        </div>
        <Actions a={a} question={question} />
      </div>
      <section className="mt-6" aria-label="Checked by Hakiki">
        <h2 className="statute flex items-center gap-2 text-lg font-medium">
          <ClipboardCheck className="h-5 w-5 text-ink-2" aria-hidden />
          Checked by Hakiki
        </h2>
        {!anyFlagged && (
          <p className="mt-2 text-ink-2">
            Hakiki found nothing to flag in what it could check. {check.length} item{check.length === 1 ? '' : 's'} checked.
          </p>
        )}
        {check.length > 0 && (
          <ul className="mt-2 space-y-3">
            {check.map((f, k) => {
              const Icon = f.flagged ? CircleAlert : Check
              return (
                <li key={k} className="step-in flex gap-2.5 border-l-2 border-rule pl-3" style={{ animationDelay: `${k * 0.06}s` }}>
                  <Icon className="mt-1 h-4 w-4 shrink-0 text-ink-2" aria-hidden />
                  <div>
                    <p>
                      <span className="text-sm text-ink-2">
                        {f.flagged ? 'Flagged' : 'Checked'} · {KIND_WORDS[f.kind] ?? f.kind}
                        {f.raw_text ? ': ' : ''}
                      </span>
                      {f.raw_text && <span className="statute">{f.kind === 'quote' ? `“${f.raw_text}”` : f.raw_text}</span>}
                    </p>
                    <p className="text-[0.95rem]">{CHECK_WORDS[f.result] ?? cap(f.note)}</p>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}

/** The answer as the model writes it: plain text, each chunk fading in. The rendered answer replaces it, so screen
 * readers hear only that (this block is hidden from them). */
function Writing({ chunks, draft }: { chunks: string[]; draft: boolean }) {
  return (
    <div className="mt-5 max-w-[68ch]">
      <p className="step-now flex items-center gap-2.5 text-[0.95rem]">
        <PenLine className="h-4 w-4 shrink-0 text-seal" aria-hidden />
        {draft ? 'Writing the draft…' : 'Writing…'}
      </p>
      <p className={`mt-3 whitespace-pre-wrap text-ink-2 ${draft ? 'statute' : ''}`} aria-hidden>
        {chunks.map((c, k) => (
          <span key={k} className="delta-in">
            {c.replace(/\*\*/g, '')}
          </span>
        ))}
      </p>
    </div>
  )
}

/** What the agent is doing, one line per tool call as it starts; the current one pulses. */
function Steps({ steps, pending }: { steps: Step[]; pending: boolean }) {
  const shown = steps.length || !pending ? steps : [{ tool: '', label: 'Reading your question' }]
  return (
    <ol className={`space-y-1.5 text-[0.95rem] ${pending ? 'text-ink' : 'text-ink-2'}`} aria-label="What Hakiki looked up">
      {shown.map((s, k) => {
        const Icon = ICONS[s.tool] ?? Sparkles
        const now = pending && k === shown.length - 1
        return (
          <li key={k} className={`step-in flex items-center gap-2.5 ${now ? 'step-now' : ''}`}>
            <Icon className={`h-4 w-4 shrink-0 ${now ? 'text-seal' : 'text-ink-2'}`} aria-hidden />
            <span>{s.label}</span>
          </li>
        )
      })}
    </ol>
  )
}

// ---- The answer: text parts carry light markdown (bold, bullets, blank-line paragraphs); the rest are references.

function AnswerBody({ parts }: { parts: Part[] }) {
  // Group lines into blocks: blank lines split paragraphs, runs of bullets become a list.
  const blocks: ReactNode[] = []
  let para: Inline[][] = []
  let list: Inline[][] = []
  const flush = () => {
    if (para.length)
      blocks.push(
        <p key={blocks.length}>
          {para.map((items, k) => (
            <Fragment key={k}>
              {k > 0 && ' '}
              <Inlines items={items} />
            </Fragment>
          ))}
        </p>,
      )
    if (list.length)
      blocks.push(
        <ul key={blocks.length} className="list-disc space-y-1.5 pl-6 marker:text-ink-2">
          {list.map((items, k) => (
            <li key={k}>
              <Inlines items={items} />
            </li>
          ))}
        </ul>,
      )
    para = []
    list = []
  }
  for (const l of toLines(parts)) {
    if ('ruling' in l) {
      flush()
      blocks.push(<Ruling key={blocks.length} r={l.ruling} />)
    } else if (isBlank(l)) flush()
    else if (l.bullet) {
      if (para.length) flush()
      list.push(l.items)
    } else {
      if (list.length) flush()
      para.push(l.items)
    }
  }
  flush()
  return <>{blocks}</>
}

function Inlines({ items }: { items: Inline[] }) {
  return items.map((x, k) => {
    if (typeof x === 'string')
      return x.split(/\*\*(.+?)\*\*/g).map((s, j) =>
        j % 2 ? (
          <strong key={`${k}-${j}`} className="font-semibold">
            {s}
          </strong>
        ) : (
          <Fragment key={`${k}-${j}`}>{s}</Fragment>
        ),
      )
    if (x.kind === 'section') return <SectionChip key={k} s={x} />
    if (x.kind === 'case') return <CaseLink key={k} c={x} />
    return (
      <span
        key={k}
        className="text-sm whitespace-nowrap text-ink-2"
        title="The model named a reference that none of Hakiki’s lookups returned, so it was taken out rather than shown unchecked."
      >
        [reference removed]
      </span>
    )
  })
}

function SectionChip({ s }: { s: SectionRef }) {
  const acted = courtActed(s.status)
  return (
    <Link
      href={sectionHref(s.provision_id)}
      title={s.heading ?? undefined}
      className="ask-chip-link inline-flex items-baseline gap-1.5 rounded-sm border border-rule bg-paper px-1.5 align-baseline text-[0.95rem] whitespace-nowrap hover:border-ink-2"
    >
      <span className="text-gazette underline underline-offset-[3px]">
        {s.act}
        {s.number && <> s.{s.number}</>}
      </span>
      <span className={`text-sm ${acted ? 'text-seal' : 'text-ink-2'}`}>{cap(s.status)}</span>
    </Link>
  )
}

function CaseLink({ c }: { c: CaseRef }) {
  const url = cleanUrl(c.url)
  const label = (
    <>
      <i>{shortCase(c.title)}</i>
      {c.citation && <> {c.citation}</>}
    </>
  )
  return url ? (
    <a href={url} className="link" target="_blank" rel="noreferrer">
      {label}
      <span className="sr-only"> (opens Kenya Law in a new tab)</span>
    </a>
  ) : (
    <span>{label}</span>
  )
}

/** A ruling quoted from the database, never by the model: the court's words, then who, where, and who checked it. */
function Ruling({ r }: { r: RulingPart }) {
  const url = cleanUrl(r.url)
  const where = locator(r.paragraph)
  const unverified = r.checked_by === 'unverified'
  return (
    <figure className={`border-l-2 py-0.5 pl-4 ${unverified ? 'border-dashed border-ink-2/50' : r.state ? 'border-rule' : 'border-seal'}`}>
      <CourtWords quote={r.quote} className={`text-lg ${r.state ? 'opacity-75' : ''}`} />
      <figcaption className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.95rem] text-ink-2">
        <span>
          {r.case ? <span className="text-ink">{shortCase(r.case)}</span> : <span className="text-ink">Parliament</span>}
          {r.citation && <> {r.citation}</>}
          {r.court && <>, {r.court}</>}
          {where && <>, {where}</>}.
        </span>
        {url && (
          <a href={url} className="link whitespace-nowrap" target="_blank" rel="noreferrer">
            Read the judgment<span className="sr-only"> (opens Kenya Law in a new tab)</span>
          </a>
        )}
        <span className={`rounded-sm border px-1.5 py-px text-xs ${unverified ? 'border-dashed border-ink-2/60' : 'border-rule'}`}>{cap(r.checked_by)}</span>
        {r.state && <span className="text-sm">{cap(r.state)}</span>}
      </figcaption>
    </figure>
  )
}
