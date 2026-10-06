'use client'
import { ArrowUp, BookOpen, Check, CircleAlert, ClipboardCheck, Copy, FileSearch, Gavel, Library, type LucideIcon, PenLine, RotateCcw, ScrollText, Search, Sparkles } from 'lucide-react'
import Link from 'next/link'
import { Fragment, type ReactNode, useEffect, useRef, useState } from 'react'
import { CourtWords } from '@/components/court'
import { cap, courtActed, sectionHref, shortCase } from '@/lib/format'
import { type Answer, type CaseRef, type CheckFlag, type ChatEvent, type Inline, isBlank, type Part, type Ruling as RulingPart, type SectionRef, type Step, toLines } from '@/lib/answer'
import { cleanUrl, locator } from '@/lib/text'

type Mode = 'answer' | 'draft'

interface Turn {
  question: string
  mode: Mode
  steps: Step[]
  answer: Answer | null
  /** The answer as it streams in (delta events), one entry per chunk; cleared by reset and by the answer. */
  live: string[]
  error: string | null
  pending: boolean
}

const EXAMPLES = [
  'Is section 204 of the Penal Code still good law?',
  'Can I be jailed for criminal defamation in Kenya?',
  'What did the court decide in Okuta?',
  'Has Sexual Offences Act s.8 been changed by the courts?',
]
const DRAFT_EXAMPLES = [
  'Draft a submission paragraph on whether s.204 of the Penal Code still requires the death sentence',
  'Draft a short paragraph on the status of criminal defamation under s.194 of the Penal Code',
  'Draft a paragraph on whether the minimum sentences in Sexual Offences Act s.8 bind the court',
]
const MAX_Q = 2000
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

export function Ask() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState('')
  const [mode, setMode] = useState<Mode>('answer')
  const last = useRef<HTMLLIElement>(null)
  const inflight = useRef<AbortController | null>(null)
  const pending = turns.some((t) => t.pending)

  // Leaving the page drops the stream, so the API stops the agent rather than answering no one.
  useEffect(() => () => inflight.current?.abort(), [])

  // A new question lands below the fold on a long conversation: bring it into view.
  useEffect(() => {
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    last.current?.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' })
  }, [turns.length])

  async function ask(question: string, prior: Turn[], mode: Mode) {
    question = question.trim().slice(0, MAX_Q)
    if (!question || pending) return
    const i = prior.length
    const history = prior
      .filter((t) => t.answer)
      .slice(-6)
      .map((t) => ({ question: t.question, answer: t.answer!.text.slice(0, 4000) }))
    setTurns([...prior, { question, mode, steps: [], answer: null, live: [], error: null, pending: true }])
    setQ('')
    const patch = (f: (t: Turn) => Partial<Turn>) => setTurns((ts) => ts.map((t, k) => (k === i ? { ...t, ...f(t) } : t)))
    const ctrl = new AbortController()
    inflight.current = ctrl
    try {
      const res = await fetch('/ask/api', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, history, mode }),
        signal: ctrl.signal,
      })
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.error ?? 'Hakiki could not answer just now. Try again in a moment.')
      }
      let answered = false
      const handle = (e: ChatEvent) => {
        if (e.type === 'step') patch((t) => ({ steps: [...t.steps, { tool: e.tool, label: e.label }] }))
        else if (e.type === 'delta') patch((t) => ({ live: [...t.live, e.text] }))
        else if (e.type === 'reset') patch(() => ({ live: [] }))
        else if (e.type === 'answer') {
          answered = true
          patch(() => ({ live: [], answer: { text: e.text, parts: e.parts, removed: e.removed, check: e.check, label: e.label } }))
        } else if (e.type === 'error') throw new Error(e.message)
      }
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
      let buf = ''
      try {
        for (;;) {
          const { value, done } = await reader.read()
          if (done) break
          buf += value
          const lines = buf.split('\n')
          buf = lines.pop()!
          for (const l of lines) if (l.trim()) handle(JSON.parse(l))
        }
        if (buf.trim()) handle(JSON.parse(buf))
      } finally {
        reader.cancel().catch(() => {}) // an error event or bad line stops reading: release the stream
      }
      if (!answered) throw new Error('The answer was cut off. Try again in a moment.')
      patch(() => ({ pending: false }))
    } catch (err) {
      if (ctrl.signal.aborted) return // the page is gone
      const message = err instanceof TypeError || err instanceof SyntaxError ? 'The connection dropped. Try again in a moment.' : (err as Error).message
      patch(() => ({ pending: false, error: message }))
    }
  }

  const retry = (i: number) => ask(turns[i].question, turns.slice(0, i), turns[i].mode)
  const examples = mode === 'draft' ? DRAFT_EXAMPLES : EXAMPLES

  return (
    <div className="pb-8">
      {turns.length > 0 && (
        <ol className="mt-4 space-y-12" aria-label="Conversation">
          {turns.map((t, i) => (
            <li key={i} ref={i === turns.length - 1 ? last : undefined} className="scroll-mt-24">
              <TurnView t={t} onRetry={i === turns.length - 1 ? () => retry(i) : undefined} />
            </li>
          ))}
        </ol>
      )}

      <form
        className="mt-10"
        onSubmit={(e) => {
          e.preventDefault()
          ask(q, turns, mode)
        }}
      >
        <div className="flex flex-wrap items-end justify-between gap-3">
          <label htmlFor="ask-q" className="statute block text-xl font-medium">
            {mode === 'draft' ? 'What should Hakiki draft?' : turns.length ? 'Ask a follow-up' : 'Your question'}
          </label>
          <ModeToggle mode={mode} onChange={setMode} />
        </div>
        <div className="mt-3 flex items-end gap-3 rounded-md border border-rule bg-paper p-2 focus-within:border-ink-2">
          <textarea
            id="ask-q"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                ask(q, turns, mode)
              }
            }}
            maxLength={MAX_Q}
            rows={2}
            placeholder={mode === 'draft' ? 'Draft a submission paragraph on…' : 'Is this section still good law? What did the court decide in…?'}
            aria-describedby="ask-hint"
            className="min-h-[3.5rem] w-full resize-y bg-transparent px-2 py-1.5 outline-none placeholder:text-ink-2/70"
          />
          <button
            type="submit"
            disabled={pending || !q.trim()}
            className="ask-send grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink text-paper disabled:opacity-35"
            aria-label={mode === 'draft' ? 'Draft' : 'Ask'}
          >
            <ArrowUp className="h-5 w-5" aria-hidden />
          </button>
        </div>
        <p id="ask-hint" className="mt-2 text-sm text-ink-2">
          {mode === 'draft'
            ? 'Hakiki drafts a short passage, then checks every case, quote and section in it. Enter to send, Shift+Enter for a new line.'
            : 'Enter to ask, Shift+Enter for a new line.'}
        </p>
        <p className="mt-1 text-sm text-ink-2">Hakiki reports what published sources say. It is not legal advice.</p>
      </form>

      {(turns.length === 0 || (mode === 'draft' && !turns.some((t) => t.mode === 'draft'))) && (
        <div className="mt-6" role="group" aria-label={mode === 'draft' ? 'Example drafting tasks' : 'Example questions'}>
          <p className="text-sm text-ink-2">Or try one of these:</p>
          <ul key={mode} className="mt-2 flex flex-wrap gap-2">
            {examples.map((ex, k) => (
              <li key={ex}>
                <button
                  type="button"
                  onClick={() => ask(ex, turns, mode)}
                  className="ask-chip rounded-full border border-note-rule bg-note px-3.5 py-1.5 text-left text-[0.95rem]"
                  style={{ ['--i' as string]: k }}
                >
                  {ex}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** onRetry only on the last turn: asking again replaces it, and an earlier one would drop the turns after it. */
function TurnView({ t, onRetry }: { t: Turn; onRetry?: () => void }) {
  return (
    <article>
      <div className="relative ml-auto w-fit max-w-[60ch]">
        <p className="statute rounded-md bg-panel px-4 py-2.5 text-lg">{t.question}</p>
        <svg
          aria-hidden="true"
          viewBox="0 0 16 14"
          className="pointer-events-none absolute top-[calc(100%-1px)] right-6 h-3.5 w-4 text-panel"
        >
          <path d="M0 0h16v14z" fill="currentColor" />
        </svg>
      </div>
      <div aria-live="polite" className="mt-5">
        {(t.pending || t.steps.length > 0) && <Steps steps={t.steps} pending={t.pending && !t.answer && !t.live.length} />}
        {!t.answer && !t.error && t.live.length > 0 && <Writing chunks={t.live} draft={t.mode === 'draft'} />}
        {t.answer && t.answer.label !== undefined ? (
          <Draft a={t.answer} />
        ) : (
          t.answer && (
            <div className="answer-in mt-5 max-w-[68ch] space-y-4">
              <AnswerBody parts={t.answer.parts} />
            </div>
          )
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

/** Answer | Draft: two toggle buttons, the pressed one is the mode. */
function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div role="group" aria-label="Mode" className="inline-flex rounded-full border border-rule bg-paper p-0.5 text-sm">
      {(['answer', 'draft'] as const).map((m) => (
        <button
          key={m}
          type="button"
          aria-pressed={mode === m}
          onClick={() => onChange(m)}
          className={`ask-mode rounded-full px-3.5 py-1 ${mode === m ? 'bg-ink text-paper' : 'text-ink-2 hover:text-ink'}`}
        >
          {m === 'answer' ? 'Answer' : 'Draft'}
        </button>
      ))}
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

/** The draft as plain citations for pasting: the label first, without the "[status: …]" and "<url>" markers. */
function draftCopy(a: Answer) {
  const body = a.text.replace(/ ?\[status: [^\]]*\]/g, '').replace(/ ?<https?:[^>\s]*>/g, '')
  return `${a.label}\n\n${body}`
}

/** A draft: the label, the draft on a sheet of paper (copy = label + plain text), then everything Hakiki checked. */
function Draft({ a }: { a: Answer }) {
  const [copy, setCopy] = useState<'idle' | 'copied' | 'failed'>('idle')
  useEffect(() => {
    if (copy === 'idle') return
    const id = setTimeout(() => setCopy('idle'), 2000)
    return () => clearTimeout(id)
  }, [copy])
  const check = a.check ?? []
  const anyFlagged = check.some((f) => f.flagged)
  const doCopy = () => {
    const p = navigator.clipboard?.writeText(draftCopy(a))
    if (!p) return setCopy('failed')
    p.then(() => setCopy('copied'), () => setCopy('failed'))
  }
  return (
    <div className="answer-in mt-5 max-w-[72ch]">
      <p className="text-sm text-ink-2">{a.label}</p>
      <div className="draft-paper relative mt-3 rounded-sm bg-paper px-6 pt-5 pb-6 shadow-[0_14px_30px_-22px_rgba(24,33,43,0.7)] ring-1 ring-rule sm:px-8">
        <button
          type="button"
          onClick={doCopy}
          className="link absolute top-3 right-3 inline-flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-sm text-ink-2 hover:text-ink"
        >
          {copy === 'copied' ? <Check className="h-4 w-4" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
          <span aria-live="polite">{copy === 'copied' ? 'Copied' : copy === 'failed' ? 'Couldn’t copy' : 'Copy text'}</span>
        </button>
        <div className="statute mt-4 space-y-4 text-[1.05rem] leading-relaxed">
          <AnswerBody parts={a.parts} />
        </div>
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
                      <span className="text-sm text-ink-2">{f.flagged ? 'Flagged' : 'Checked'} · {KIND_WORDS[f.kind] ?? f.kind}{f.raw_text ? ': ' : ''}</span>
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
    if (para.length) blocks.push(<p key={blocks.length}>{para.map((items, k) => <Fragment key={k}>{k > 0 && ' '}<Inlines items={items} /></Fragment>)}</p>)
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
      return x.split(/\*\*(.+?)\*\*/g).map((s, j) => (j % 2 ? <strong key={`${k}-${j}`} className="font-semibold">{s}</strong> : <Fragment key={`${k}-${j}`}>{s}</Fragment>))
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
