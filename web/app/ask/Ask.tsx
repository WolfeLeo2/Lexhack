'use client'
import { ArrowUp, BookOpen, FileSearch, Gavel, Library, type LucideIcon, RotateCcw, ScrollText, Search, Sparkles } from 'lucide-react'
import Link from 'next/link'
import { Fragment, type ReactNode, useEffect, useRef, useState } from 'react'
import { CourtWords } from '@/components/court'
import { cap, courtActed, sectionHref, shortCase } from '@/lib/format'
import { type Answer, type CaseRef, type ChatEvent, type Inline, isBlank, type Part, type Ruling as RulingPart, type SectionRef, type Step, toLines } from '@/lib/answer'
import { cleanUrl, locator } from '@/lib/text'

interface Turn {
  question: string
  steps: Step[]
  answer: Answer | null
  error: string | null
  pending: boolean
}

const EXAMPLES = [
  'Is section 204 of the Penal Code still good law?',
  'Can I be jailed for criminal defamation in Kenya?',
  'What did the court decide in Okuta?',
  'Has Sexual Offences Act s.8 been changed by the courts?',
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
}

export function Ask() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState('')
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

  async function ask(question: string, prior: Turn[]) {
    question = question.trim().slice(0, MAX_Q)
    if (!question || pending) return
    const i = prior.length
    const history = prior
      .filter((t) => t.answer)
      .slice(-6)
      .map((t) => ({ question: t.question, answer: t.answer!.text.slice(0, 4000) }))
    setTurns([...prior, { question, steps: [], answer: null, error: null, pending: true }])
    setQ('')
    const patch = (f: (t: Turn) => Partial<Turn>) => setTurns((ts) => ts.map((t, k) => (k === i ? { ...t, ...f(t) } : t)))
    const ctrl = new AbortController()
    inflight.current = ctrl
    try {
      const res = await fetch('/ask/api', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, history }),
        signal: ctrl.signal,
      })
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.error ?? 'Hakiki could not answer just now. Try again in a moment.')
      }
      let answered = false
      const handle = (e: ChatEvent) => {
        if (e.type === 'step') patch((t) => ({ steps: [...t.steps, { tool: e.tool, label: e.label }] }))
        else if (e.type === 'answer') {
          answered = true
          patch(() => ({ answer: { text: e.text, parts: e.parts, removed: e.removed } }))
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

  const retry = (i: number) => ask(turns[i].question, turns.slice(0, i))

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
          ask(q, turns)
        }}
      >
        <label htmlFor="ask-q" className="statute block text-xl font-medium">
          {turns.length ? 'Ask a follow-up' : 'Your question'}
        </label>
        <div className="mt-3 flex items-end gap-3 rounded-md border border-rule bg-paper p-2 focus-within:border-ink-2">
          <textarea
            id="ask-q"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                ask(q, turns)
              }
            }}
            maxLength={MAX_Q}
            rows={2}
            placeholder="Is this section still good law? What did the court decide in…?"
            aria-describedby="ask-hint"
            className="min-h-[3.5rem] w-full resize-y bg-transparent px-2 py-1.5 outline-none placeholder:text-ink-2/70"
          />
          <button
            type="submit"
            disabled={pending || !q.trim()}
            className="ask-send grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink text-paper disabled:opacity-35"
            aria-label="Ask"
          >
            <ArrowUp className="h-5 w-5" aria-hidden />
          </button>
        </div>
        <p id="ask-hint" className="mt-2 text-sm text-ink-2">
          Enter to ask, Shift+Enter for a new line.
        </p>
        <p className="mt-1 text-sm text-ink-2">Hakiki reports what published sources say. It is not legal advice.</p>
      </form>

      {turns.length === 0 && (
        <div className="mt-6" role="group" aria-label="Example questions">
          <p className="text-sm text-ink-2">Or try one of these:</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {EXAMPLES.map((ex, k) => (
              <li key={ex}>
                <button
                  type="button"
                  onClick={() => ask(ex, turns)}
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
      <p className="statute ml-auto w-fit max-w-[60ch] rounded-md bg-panel px-4 py-2.5 text-lg">{t.question}</p>
      <div aria-live="polite" className="mt-5">
        {(t.pending || t.steps.length > 0) && <Steps steps={t.steps} pending={t.pending && !t.answer} />}
        {t.answer && (
          <div className="answer-in mt-5 max-w-[68ch] space-y-4">
            <AnswerBody parts={t.answer.parts} />
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
