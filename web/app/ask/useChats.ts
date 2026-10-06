'use client'
// Ask Hakiki's chats, kept in this browser only (localStorage), never on Hakiki's servers. One versioned key; the open
// chat is per tab (sessionStorage). Saved when no answer is streaming, and on leaving the page, so a chunk-by-chunk
// stream doesn't rewrite storage and a reload mid-answer keeps the question, marked as interrupted.
import { useCallback, useEffect, useRef, useState } from 'react'
import type { Answer, Step } from '@/lib/answer'

export type Mode = 'answer' | 'draft'

export interface Turn {
  question: string
  mode: Mode
  steps: Step[]
  answer: Answer | null
  /** The answer as it streams in (delta events), one entry per chunk; cleared by reset and by the answer. */
  live: string[]
  error: string | null
  pending: boolean
}

export interface Chat {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  turns: Turn[]
}

/** 'saved' | 'trimmed' (storage full: the oldest chats weren't kept) | 'off' (storage refused: private mode, disabled). */
export type Store = 'loading' | 'saved' | 'trimmed' | 'off'

const KEY = 'hakiki:ask:v1'
const LEGACY = 'hakiki:ask:sessions' // the first, unversioned store (same shape)
const ACTIVE = 'hakiki:ask:active'
export const MAX_CHATS = 30
export const INTERRUPTED = 'This answer was interrupted before it finished.'

export const byRecent = (a: Chat, b: Chat) => b.updatedAt - a.updatedAt
export const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8) // randomUUID needs https

/** A stored chat, or null when it isn't one (an older or foreign shape): dropped, never rendered. */
function valid(c: unknown): Chat | null {
  const x = c as Chat
  if (!x || typeof x.id !== 'string' || typeof x.title !== 'string' || !Array.isArray(x.turns)) return null
  const turns = x.turns.filter((t) => t && typeof t.question === 'string' && Array.isArray(t.steps))
  if (!turns.length) return null
  return {
    id: x.id,
    title: x.title,
    createdAt: Number(x.createdAt) || 0,
    updatedAt: Number(x.updatedAt) || 0,
    turns: turns.map((t) => settle({ ...t, mode: t.mode === 'draft' ? 'draft' : 'answer', live: [] })),
  }
}

/** A turn as stored: one still streaming (or left without an answer) is saved as interrupted, so it can be asked again. */
function settle(t: Turn): Turn {
  if (!t.pending && (t.answer || t.error)) return t
  return { ...t, pending: false, live: [], answer: t.answer ?? null, error: t.answer ? null : (t.error ?? INTERRUPTED) }
}

function read(): Chat[] {
  const raw = localStorage.getItem(KEY)
  const data = raw ? JSON.parse(raw)?.chats : JSON.parse(localStorage.getItem(LEGACY) ?? '[]')
  return Array.isArray(data) ? data.map(valid).filter((c): c is Chat => !!c).sort(byRecent) : []
}

/** Write the chats, dropping the oldest until they fit. */
function save(chats: Chat[]): Store {
  let list = [...chats].sort(byRecent).slice(0, MAX_CHATS)
  for (;;) {
    try {
      const json = JSON.stringify({ v: 1, chats: list.map((c) => ({ ...c, turns: c.turns.map(settle) })) })
      if (localStorage.getItem(KEY) !== json) localStorage.setItem(KEY, json) // equal: another tab wrote it
      localStorage.removeItem(LEGACY)
      return list.length < chats.length ? 'trimmed' : 'saved'
    } catch {
      if (list.length <= 1) return 'off'
      list = list.slice(0, -1)
    }
  }
}

export function useChats() {
  const [chats, setChats] = useState<Chat[]>([])
  const [activeId, setActiveIdState] = useState<string | null>(null)
  const [store, setStore] = useState<Store>('loading')
  const latest = useRef({ chats, loaded: false })

  // Restore once on the client: the server render has no chats, so there is nothing to mismatch.
  useEffect(() => {
    let restored: Chat[] = []
    let active: string | null = null
    let ok = true
    try {
      restored = read()
      active = sessionStorage.getItem(ACTIVE)
    } catch {
      ok = false
    }
    latest.current = { chats: restored, loaded: true }
    /* eslint-disable react-hooks/set-state-in-effect -- reading the browser's storage after mount is the point */
    setChats(restored)
    setActiveIdState(active && restored.some((c) => c.id === active) ? active : null)
    setStore(ok ? 'saved' : 'off')
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [])

  // Save when nothing is streaming (a stream changes the chats on every chunk).
  useEffect(() => {
    if (store === 'loading') return // the first render's empty list must never overwrite what is stored
    latest.current = { chats, loaded: true }
    if (chats.some((c) => c.turns.some((t) => t.pending))) return
    const s = save(chats)
    if (s !== store) setStore(s) // eslint-disable-line react-hooks/set-state-in-effect
  }, [chats, store])

  // Leaving or reloading mid-answer: save now, the streaming turn as interrupted.
  useEffect(() => {
    const flush = () => latest.current.loaded && save(latest.current.chats)
    window.addEventListener('pagehide', flush)
    return () => {
      window.removeEventListener('pagehide', flush)
      flush()
    }
  }, [])

  // Another tab saved: take its list (it is newer), keeping any chat this tab is still answering.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== KEY) return
      let theirs: Chat[]
      try {
        theirs = read()
      } catch {
        return
      }
      setChats((prev) => {
        const mine = prev.filter((c) => c.turns.some((t) => t.pending))
        return [...mine, ...theirs.filter((c) => !mine.some((m) => m.id === c.id))].sort(byRecent)
      })
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const setActiveId = useCallback((id: string | null) => {
    setActiveIdState(id)
    try {
      if (id) sessionStorage.setItem(ACTIVE, id)
      else sessionStorage.removeItem(ACTIVE)
    } catch {}
  }, [])

  return { chats, setChats, activeId, setActiveId, store }
}
