'use client'
// Earlier chats: one list, shown on the empty page and in a side sheet (a native <dialog>: focus moves in, is trapped,
// Escape closes it, focus returns to the button that opened it).
import { Plus, Undo2, X } from 'lucide-react'
import { type ReactNode, useEffect, useRef } from 'react'
import type { Chat, Store } from './useChats'

function timeAgo(ms: number): string {
  const min = Math.floor(Math.max(0, Date.now() - ms) / 60_000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min} min ago`
  const h = Math.floor(min / 60)
  if (h < 24) return `${h} h ago`
  const d = Math.floor(h / 24)
  if (d === 1) return 'yesterday'
  if (d < 7) return `${d} days ago`
  return new Date(ms).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: d > 300 ? 'numeric' : undefined })
}

const STORE_WORDS: Record<Store, string> = {
  loading: '',
  saved: 'Kept only in this browser. Hakiki’s servers don’t store your chats; a follow-up sends the last few questions and answers along with it.',
  trimmed: 'This browser’s storage is full, so the oldest chats weren’t kept. Remove a few to make room.',
  off: 'This browser isn’t letting Hakiki keep chats (private browsing or storage turned off), so they’ll be gone when you leave the page.',
}

export const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`

interface ListProps {
  chats: Chat[]
  activeId: string | null
  store: Store
  removed: Chat[] | null
  onOpen: (id: string) => void
  onRemove: (id: string) => void
  onClearAll: () => void
  onUndo: () => void
}

/** The chats, newest first, each with a Remove button beside it (not inside it); Undo after a removal. */
export function ChatList({ chats, activeId, store, removed, onOpen, onRemove, onClearAll, onUndo }: ListProps) {
  return (
    <div>
      {removed && (
        <p role="status" className="step-in mb-3 flex flex-wrap items-center gap-x-3 rounded-md border border-note-rule bg-note px-3 py-2 text-sm">
          <span className="min-w-0 truncate">{removed.length === 1 ? `Removed “${removed[0].title}”.` : `Removed ${plural(removed.length, 'chat')}.`}</span>
          <button type="button" onClick={onUndo} className="link inline-flex items-center gap-1 text-gazette underline underline-offset-[3px]">
            <Undo2 className="h-3.5 w-3.5" aria-hidden />
            Undo
          </button>
        </p>
      )}
      {chats.length > 0 ? (
        <ol className="divide-y divide-rule border-y border-rule">
          {chats.map((c) => {
            const active = c.id === activeId
            const draft = c.turns.some((t) => t.mode === 'draft')
            return (
              <li key={c.id} className="flex items-start gap-1">
                <button
                  type="button"
                  onClick={() => onOpen(c.id)}
                  aria-current={active ? 'page' : undefined}
                  className={`group min-w-0 flex-1 border-l-2 py-3 pr-2 pl-3 text-left transition-colors hover:bg-panel/60 ${active ? 'border-seal bg-panel/60' : 'border-transparent'}`}
                >
                  <span className="statute line-clamp-2 text-lg leading-snug break-words text-ink transition-colors group-hover:text-gazette">{c.title}</span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-ink-2">
                    {draft && <span className="rounded-sm border border-rule px-1.5 text-xs">Draft</span>}
                    <span>{plural(c.turns.length, 'question')}</span>
                    <span aria-hidden>·</span>
                    <span>{timeAgo(c.updatedAt)}</span>
                    {active && <span className="sr-only">(open now)</span>}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => onRemove(c.id)}
                  aria-label={`Remove “${c.title}”`}
                  title="Remove this chat"
                  className="mt-2.5 shrink-0 rounded-sm p-2 text-ink-2 transition-colors hover:bg-panel hover:text-ink"
                >
                  <X className="h-4 w-4" aria-hidden />
                </button>
              </li>
            )
          })}
        </ol>
      ) : (
        <p className="border-y border-rule py-8 text-center text-ink-2">No chats yet. Ask a question and it will be kept here.</p>
      )}
      <div className="mt-3 flex flex-wrap items-start justify-between gap-x-6 gap-y-2 text-sm text-ink-2">
        <p className="max-w-[52ch]">{STORE_WORDS[store]}</p>
        {chats.length > 1 && (
          <button type="button" onClick={onClearAll} className="link shrink-0 underline underline-offset-[3px] hover:text-ink">
            Remove all {chats.length}
          </button>
        )}
      </div>
    </div>
  )
}

/** The chat list in a side sheet, opened from inside a chat. */
export function HistorySheet({ open, onClose, onNew, children }: { open: boolean; onClose: () => void; onNew: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (open && !d?.open) d?.showModal()
    if (!open && d?.open) d.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()} // the backdrop
      aria-labelledby="chats-h"
      className="history-sheet paper-grain fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-dvh w-full max-w-md border-l border-rule bg-paper p-0 text-ink shadow-[-8px_0_24px_-12px_rgba(24,33,43,0.35)] backdrop:bg-ink/30"
    >
      <div className="flex h-full flex-col p-6 sm:p-8">
        <div className="flex items-start justify-between gap-4 border-b border-rule pb-4">
          <h2 id="chats-h" className="statute text-2xl font-medium tracking-tight">
            Your chats
          </h2>
          <button type="button" onClick={onClose} className="rounded-sm border border-rule px-2.5 py-1 text-sm text-ink-2 hover:border-ink hover:text-ink">
            Close
          </button>
        </div>
        <button
          type="button"
          onClick={onNew}
          className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-sm border border-rule bg-panel px-4 py-2.5 text-sm font-medium transition-colors hover:border-ink"
        >
          <Plus className="h-4 w-4" aria-hidden />
          New chat
        </button>
        <div className="mt-4 -mr-2 flex-1 overflow-y-auto pr-2">{children}</div>
      </div>
    </dialog>
  )
}
