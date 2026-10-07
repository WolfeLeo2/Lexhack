'use client'
import { ArrowUp, History, Plus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ChatEvent } from '@/lib/answer'
import { TurnView } from './AnswerView'
import { ChatList, HistorySheet, plural } from './History'
import { byRecent, type Chat, type Mode, newId, type Turn, useChats } from './useChats'

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
const STOPPED = 'Stopped before the answer finished.'
const stamp = () => Date.now() // only ever called from handlers; the compiler can't tell

export function Ask() {
  const { chats, setChats, activeId, setActiveId, store } = useChats()
  const [sheet, setSheet] = useState(false)
  const [removed, setRemoved] = useState<Chat[] | null>(null)
  const [q, setQ] = useState('')
  const [mode, setMode] = useState<Mode>('answer')
  const last = useRef<HTMLLIElement>(null)
  const scrollOnAsk = useRef(false)
  const inflight = useRef<AbortController | null>(null)

  const active = chats.find((c) => c.id === activeId) ?? null
  const turns = active?.turns ?? []
  const pending = turns.some((t) => t.pending)
  const sorted = [...chats].sort(byRecent)

  // Leaving the page drops the stream, so the API stops the agent rather than answering no one.
  useEffect(() => () => inflight.current?.abort(), [])

  // Bring a new question into view; opening a chat or reloading leaves the page where it is.
  useEffect(() => {
    if (!scrollOnAsk.current) return
    scrollOnAsk.current = false
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    last.current?.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' })
  }, [turns.length])

  /** Open a chat (null = a new one). A stream in progress stops; its turn is marked so it can be asked again. */
  function open(id: string | null) {
    if (id !== activeId) inflight.current?.abort()
    setActiveId(id)
    setSheet(false)
    setQ('')
    const c = chats.find((x) => x.id === id)
    if (c) setMode(c.turns[c.turns.length - 1].mode)
  }

  function remove(ids: string[]) {
    if (activeId && ids.includes(activeId)) open(null)
    setRemoved(chats.filter((c) => ids.includes(c.id)))
    setChats((prev) => prev.filter((c) => !ids.includes(c.id)))
  }

  function undo() {
    const back = removed ?? []
    setChats((prev) => [...prev, ...back.filter((c) => !prev.some((p) => p.id === c.id))])
    setRemoved(null)
  }

  async function ask(question: string, prior: Turn[], m: Mode) {
    question = question.trim().slice(0, MAX_Q)
    if (!question || pending) return
    const id = active?.id ?? newId()
    const i = prior.length
    const now = stamp()
    const history = prior
      .filter((t) => t.answer)
      .slice(-6)
      .map((t) => ({ question: t.question, answer: t.answer!.text.slice(0, 4000) }))
    const turn: Turn = { question, mode: m, steps: [], answer: null, live: [], error: null, pending: true }
    // prior + the new turn: asking again replaces the failed last turn rather than adding after it
    setChats((prev) =>
      prev.some((c) => c.id === id)
        ? prev.map((c) => (c.id === id ? { ...c, updatedAt: now, turns: [...prior, turn] } : c))
        : [{ id, title: question, createdAt: now, updatedAt: now, turns: [...prior, turn] }, ...prev],
    )
    if (!active) setActiveId(id)
    setQ('')
    setRemoved(null)
    scrollOnAsk.current = true

    const patch = (f: (t: Turn) => Partial<Turn>) =>
      setChats((prev) => prev.map((c) => (c.id === id ? { ...c, updatedAt: stamp(), turns: c.turns.map((t, k) => (k === i ? { ...t, ...f(t) } : t)) } : c)))

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
      if (ctrl.signal.aborted) return patch((t) => ({ pending: false, live: [], error: t.answer ? null : STOPPED }))
      const message = err instanceof TypeError || err instanceof SyntaxError ? 'The connection dropped. Try again in a moment.' : (err as Error).message
      patch(() => ({ pending: false, live: [], error: message }))
    }
  }

  const retry = (i: number) => ask(turns[i].question, turns.slice(0, i), turns[i].mode)
  const examples = mode === 'draft' ? DRAFT_EXAMPLES : EXAMPLES
  const loading = store === 'loading'
  const list = (
    <ChatList
      chats={sorted}
      activeId={activeId}
      store={store}
      removed={removed}
      onOpen={open}
      onRemove={(id) => remove([id])}
      onClearAll={() => remove(chats.map((c) => c.id))}
      onUndo={undo}
    />
  )

  return (
    <div className="pb-8">
      {active && (
        <div className="mb-8 flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-rule pb-4">
          <p className="text-sm text-ink-2">
            {plural(turns.length, 'question')} in this chat{store === 'off' ? ' · not kept after you leave' : ' · kept in this browser'}
          </p>
          <div className="flex items-center gap-2 text-sm">
            <button
              type="button"
              onClick={() => open(null)}
              className="inline-flex items-center gap-1.5 rounded-sm border border-rule bg-paper px-3 py-1.5 transition-colors hover:border-ink"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden />
              New chat
            </button>
            <button
              type="button"
              onClick={() => {
                setRemoved(null) // a stale Undo would take focus from the sheet
                setSheet(true)
              }}
              aria-haspopup="dialog"
              className="inline-flex items-center gap-1.5 rounded-sm border border-rule bg-panel px-3 py-1.5 text-ink-2 transition-colors hover:border-ink hover:text-ink"
            >
              <History className="h-3.5 w-3.5" aria-hidden />
              Your chats ({chats.length})
            </button>
          </div>
        </div>
      )}

      {turns.length > 0 && (
        <ol className="space-y-12" aria-label="Conversation">
          {turns.map((t, i) => (
            <li key={i} ref={i === turns.length - 1 ? last : undefined} className="scroll-mt-24">
              <TurnView t={t} onRetry={i === turns.length - 1 && !pending ? () => retry(i) : undefined} />
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

      {!loading && (turns.length === 0 || (mode === 'draft' && !turns.some((t) => t.mode === 'draft'))) && (
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

      {!loading && !active && (chats.length > 0 || removed) && (
        <section className="mt-14 border-t border-rule pt-8" aria-labelledby="earlier-h">
          <h2 id="earlier-h" className="statute mb-5 text-2xl font-medium tracking-[-0.01em]">
            Your earlier chats
          </h2>
          {list}
        </section>
      )}

      <HistorySheet open={sheet && !!active} onClose={() => setSheet(false)} onNew={() => open(null)}>
        {sheet && active && list}
      </HistorySheet>
    </div>
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
