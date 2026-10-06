'use client'
import { ArrowUp, BookOpen, Check, CircleAlert, ClipboardCheck, Copy, FileSearch, Gavel, Library, type LucideIcon, PenLine, Plus, RotateCcw, ScrollText, Search, Sparkles } from 'lucide-react'
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

interface ChatSession {
  id: string
  title: string
  mode: Mode
  createdAt: number
  updatedAt: number
  turns: Turn[]
}

function timeAgo(ms: number): string {
  const diffSec = Math.max(0, Math.floor((Date.now() - ms) / 1000))
  if (diffSec < 60) return 'Just now'
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHours = Math.floor(diffMin / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  return new Date(ms).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
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
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [hydrated, setHydrated] = useState(false)
  const [q, setQ] = useState('')
  const [mode, setMode] = useState<Mode>('answer')
  const last = useRef<HTMLLIElement>(null)
  const inflight = useRef<AbortController | null>(null)

  const activeSession = sessions.find((s) => s.id === activeId) ?? null
  const turns = activeSession ? activeSession.turns : []
  const pending = turns.some((t) => t.pending)

  // Restore sessions from localStorage on client mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem('hakiki:ask:sessions')
      const savedActiveId = localStorage.getItem('hakiki:ask:active_id')
      if (raw) {
        const parsed = JSON.parse(raw) as ChatSession[]
        if (Array.isArray(parsed) && parsed.length > 0) {
          const clean = parsed.map((s) => ({
            ...s,
            turns: (s.turns || []).map((t) => ({ ...t, pending: false, live: [] })),
          }))
          setSessions(clean)
          if (savedActiveId && clean.some((s) => s.id === savedActiveId)) {
            setActiveId(savedActiveId)
          }
        }
      }
    } catch {}
    setHydrated(true)
  }, [])

  // Sync sessions & activeId to localStorage
  useEffect(() => {
    if (!hydrated) return
    try {
      if (sessions.length === 0) {
        localStorage.removeItem('hakiki:ask:sessions')
        localStorage.removeItem('hakiki:ask:active_id')
      } else {
        const toStore = sessions.slice(0, 25).map((s) => ({
          ...s,
          turns: s.turns.map((t) => ({ ...t, pending: false, live: [] })),
        }))
        localStorage.setItem('hakiki:ask:sessions', JSON.stringify(toStore))
        if (activeId) {
          localStorage.setItem('hakiki:ask:active_id', activeId)
        } else {
          localStorage.removeItem('hakiki:ask:active_id')
        }
      }
    } catch {}
  }, [sessions, activeId, hydrated])

  // Sync activeSession's mode
  useEffect(() => {
    if (activeSession) {
      setMode(activeSession.mode)
    }
  }, [activeId])

  // Close history drawer on Escape key
  useEffect(() => {
    if (!showHistory) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowHistory(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [showHistory])

  // Leaving the page drops the stream, so the API stops the agent rather than answering no one.
  useEffect(() => () => inflight.current?.abort(), [])

  // A new question lands below the fold on a long conversation: bring it into view.
  useEffect(() => {
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    last.current?.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' })
  }, [turns.length])

  function startNewChat() {
    inflight.current?.abort()
    setActiveId(null)
    setQ('')
    setShowHistory(false)
  }

  function switchSession(id: string) {
    if (id === activeId) {
      setShowHistory(false)
      return
    }
    inflight.current?.abort()
    setActiveId(id)
    setShowHistory(false)
    setQ('')
  }

  function deleteSession(id: string, e?: React.MouseEvent) {
    e?.stopPropagation()
    if (activeId === id) {
      inflight.current?.abort()
      setActiveId(null)
    }
    setSessions((prev) => prev.filter((s) => s.id !== id))
  }

  function clearAllSessions() {
    inflight.current?.abort()
    setActiveId(null)
    setSessions([])
    setShowHistory(false)
  }

  async function ask(question: string, prior: Turn[], m: Mode) {
    question = question.trim().slice(0, MAX_Q)
    if (!question || pending) return

    let currentSessionId = activeId
    if (!currentSessionId) {
      currentSessionId = crypto.randomUUID()
      const newSession: ChatSession = {
        id: currentSessionId,
        title: question.length > 55 ? question.slice(0, 52) + '…' : question,
        mode: m,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        turns: [],
      }
      setSessions((prev) => [newSession, ...prev])
      setActiveId(currentSessionId)
    }

    const i = prior.length
    const history = prior
      .filter((t) => t.answer)
      .slice(-6)
      .map((t) => ({ question: t.question, answer: t.answer!.text.slice(0, 4000) }))

    const newTurn: Turn = { question, mode: m, steps: [], answer: null, live: [], error: null, pending: true }

    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== currentSessionId) return s
        return {
          ...s,
          updatedAt: Date.now(),
          turns: [...s.turns, newTurn],
        }
      })
    )
    setQ('')

    const patch = (f: (t: Turn) => Partial<Turn>) => {
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== currentSessionId) return s
          return {
            ...s,
            updatedAt: Date.now(),
            turns: s.turns.map((t, k) => (k === i ? { ...t, ...f(t) } : t)),
          }
        })
      )
    }

    const ctrl = new AbortController()
    inflight.current = ctrl
    try {
      const res = await fetch('/ask/api', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, history, mode: m }),
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
        reader.cancel().catch(() => {})
      }
      if (!answered) throw new Error('The answer was cut off. Try again in a moment.')
      patch(() => ({ pending: false }))
    } catch (err) {
      if (ctrl.signal.aborted) return
      const message = err instanceof TypeError || err instanceof SyntaxError ? 'The connection dropped. Try again in a moment.' : (err as Error).message
      patch(() => ({ pending: false, error: message }))
    }
  }

  const retry = (i: number) => ask(turns[i].question, turns.slice(0, i), turns[i].mode)
  const examples = mode === 'draft' ? DRAFT_EXAMPLES : EXAMPLES

  return (
    <div className="pb-8">
      {/* Active Inquiry Header */}
      {turns.length > 0 && (
        <header className="mb-8 border-b border-rule pb-5">
          <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-2">
                <span className="rounded-sm border border-rule px-1.5 py-px font-sans">
                  {activeSession?.mode === 'draft' ? 'Draft submission' : 'Legal inquiry'}
                </span>
                <span className="text-rule">&middot;</span>
                <span>{turns.length} {turns.length === 1 ? 'question' : 'questions'}</span>
                <span className="text-rule">&middot;</span>
                <span>Updated {timeAgo(activeSession?.updatedAt ?? Date.now())}</span>
              </div>
              <h2 className="statute mt-2.5 text-2xl sm:text-3xl font-medium tracking-tight text-ink line-clamp-2" title={activeSession?.title}>
                {activeSession?.title}
              </h2>
            </div>

            <div className="flex items-center gap-2 sm:gap-3 shrink-0 pt-1 text-sm">
              <button
                type="button"
                onClick={startNewChat}
                className="inline-flex items-center gap-1.5 rounded-sm border border-rule bg-paper px-3 py-1.5 text-sm text-ink hover:border-ink hover:text-ink transition-colors"
              >
                <Plus className="h-3.5 w-3.5" aria-hidden />
                <span>New inquiry</span>
              </button>
              {sessions.length > 1 && (
                <button
                  type="button"
                  onClick={() => setShowHistory(true)}
                  className="inline-flex items-center gap-1.5 rounded-sm border border-rule bg-panel px-3 py-1.5 text-sm text-ink-2 hover:border-ink hover:text-ink transition-colors"
                >
                  <ScrollText className="h-3.5 w-3.5" aria-hidden />
                  <span>Register ({sessions.length})</span>
                </button>
              )}
            </div>
          </div>
        </header>
      )}

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
          <div className="flex items-center gap-2">
            <ModeToggle mode={mode} onChange={setMode} />
          </div>
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

      {/* Previous inquiries ledger shown when starting fresh */}
      {turns.length === 0 && sessions.length > 0 && (
        <section className="mt-14 border-t border-rule pt-8" aria-labelledby="inquiries-h">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h2 id="inquiries-h" className="statute text-2xl font-medium tracking-[-0.01em]">
                Previous inquiries
              </h2>
              <p className="mt-1 text-sm text-ink-2">
                Saved in your browser’s local records. Open any inquiry to resume.
              </p>
            </div>
            <button
              type="button"
              onClick={clearAllSessions}
              className="text-xs text-ink-2/60 hover:text-seal transition-colors"
            >
              Clear register ({sessions.length})
            </button>
          </div>

          <ol className="mt-6 divide-y divide-rule border-y border-rule">
            {sessions.map((s) => (
              <li key={s.id} className="group">
                <div
                  onClick={() => switchSession(s.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      switchSession(s.id)
                    }
                  }}
                  className="grid grid-cols-[minmax(0,1fr)] items-baseline gap-x-6 gap-y-2 py-4 hover:bg-panel/60 sm:grid-cols-[minmax(0,1fr)_auto] cursor-pointer transition-colors"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="statute text-xl text-ink group-hover:text-gazette transition-colors line-clamp-1">
                        {s.title}
                      </span>
                      <span className="rounded-sm border border-rule px-1.5 py-px text-xs text-ink-2 shrink-0">
                        {s.mode === 'draft' ? 'Draft' : 'Inquiry'}
                      </span>
                    </div>
                    <p className="mt-1.5 text-sm text-ink-2">
                      <span>{s.turns.length} {s.turns.length === 1 ? 'question' : 'questions'}</span>
                      <span className="mx-2 text-rule">&middot;</span>
                      <span>Updated {timeAgo(s.updatedAt)}</span>
                    </p>
                  </div>

                  <div className="flex items-center gap-4 text-sm sm:justify-end">
                    <span className="text-gazette group-hover:underline underline-offset-4 text-[0.95rem]">
                      Open &rarr;
                    </span>
                    <button
                      type="button"
                      onClick={(e) => deleteSession(s.id, e)}
                      className="text-xs text-ink-2/40 hover:text-seal transition-colors py-1 px-1.5"
                      title="Remove this inquiry"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Inquiry Register Drawer */}
      {showHistory && (
        <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Inquiry register">
          <div
            className="fixed inset-0 bg-ink/30 transition-opacity"
            onClick={() => setShowHistory(false)}
          />
          <aside className="paper-grain relative z-10 w-full max-w-lg border-l border-rule bg-paper p-6 sm:p-8 flex flex-col h-full overflow-hidden shadow-[-8px_0_24px_-12px_rgba(24,33,43,0.35)]">
            <div className="flex items-start justify-between border-b border-rule pb-4 mb-5">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="statute text-2xl font-medium tracking-tight text-ink">Inquiry register</h2>
                  <span className="rounded-sm border border-rule px-1.5 py-px text-xs text-ink-2">
                    {sessions.length}
                  </span>
                </div>
                <p className="text-xs text-ink-2 mt-1">
                  Saved inquiries in this browser
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowHistory(false)}
                className="rounded-sm border border-rule px-2 py-1 text-xs text-ink-2 hover:border-ink hover:text-ink transition-colors"
                aria-label="Close register"
              >
                Close
              </button>
            </div>

            <div className="mb-4">
              <button
                type="button"
                onClick={startNewChat}
                className="w-full inline-flex items-center justify-center gap-2 rounded-sm border border-rule bg-panel hover:border-ink hover:text-ink px-4 py-2.5 text-sm font-medium transition-colors"
              >
                <Plus className="h-4 w-4" />
                <span>Start a new inquiry</span>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto divide-y divide-rule border-y border-rule pr-1 -mr-1">
              {sessions.length === 0 ? (
                <p className="text-center text-sm text-ink-2 py-12">No inquiries recorded yet.</p>
              ) : (
                sessions.map((s) => {
                  const isActive = s.id === activeId
                  return (
                    <div
                      key={s.id}
                      onClick={() => switchSession(s.id)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          switchSession(s.id)
                        }
                      }}
                      className={`group cursor-pointer py-3.5 px-3 transition-colors flex items-start justify-between gap-3 text-left ${
                        isActive
                          ? 'border-l-2 border-seal bg-panel/75'
                          : 'hover:bg-panel/40'
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="statute font-medium text-lg text-ink truncate group-hover:text-gazette transition-colors">
                          {s.title}
                        </p>
                        <p className="text-xs text-ink-2 mt-1">
                          <span className="capitalize">{s.mode === 'draft' ? 'Draft' : 'Inquiry'}</span>
                          <span className="mx-1.5 text-rule">&middot;</span>
                          <span>{s.turns.length} {s.turns.length === 1 ? 'question' : 'questions'}</span>
                          <span className="mx-1.5 text-rule">&middot;</span>
                          <span>{timeAgo(s.updatedAt)}</span>
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => deleteSession(s.id, e)}
                        aria-label={`Remove inquiry ${s.title}`}
                        title="Remove inquiry"
                        className="text-xs text-ink-2/30 hover:text-seal opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity py-1 px-1.5"
                      >
                        Remove
                      </button>
                    </div>
                  )
                })
              )}
            </div>

            {sessions.length > 0 && (
              <div className="border-t border-rule pt-4 mt-4 flex items-center justify-between text-xs text-ink-2">
                <span>{sessions.length} saved {sessions.length === 1 ? 'inquiry' : 'inquiries'}</span>
                <button
                  type="button"
                  onClick={clearAllSessions}
                  className="hover:text-seal transition-colors"
                >
                  Clear all
                </button>
              </div>
            )}
          </aside>
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
