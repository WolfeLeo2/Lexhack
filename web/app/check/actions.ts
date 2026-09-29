'use server'
import { API_URL, type CheckReport } from '@/lib/api'

export interface CheckState {
  text: string // the text that was checked, which the report's offsets refer to
  report: CheckReport | null
  error: string | null
}

export async function checkFiling(_prev: CheckState, form: FormData): Promise<CheckState> {
  // A textarea submits \r\n; normalise so the offsets the API returns match the text the report is drawn from.
  const text = String(form.get('text') ?? '').replace(/\r\n?/g, '\n')
  if (!text.trim()) return { text, report: null, error: 'Paste a filing first.' }
  try {
    const res = await fetch(`${API_URL}/api/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      cache: 'no-store',
    })
    if (res.status === 413) return { text, report: null, error: 'That filing is too long: the limit is 200,000 characters.' }
    if (!res.ok) return { text, report: null, error: `The checker answered ${res.status}. Try again in a moment.` }
    return { text, report: await res.json(), error: null }
  } catch {
    return { text, report: null, error: 'The checker is unreachable. Try again in a moment.' }
  }
}

const MAX_UPLOAD = 4 * 1024 * 1024 // Vercel caps function bodies at ~4.5 MB; the API itself takes 10 MB

export type ReadResult = { text: string; kind: 'pdf' | 'docx' | 'text'; pages: number | null; name: string } | { error: string }

/** Read an uploaded filing's text on the server (api/extract.py). The file is not stored. */
export async function readFiling(form: FormData): Promise<ReadResult> {
  const file = form.get('file')
  if (!(file instanceof File) || !file.size) return { error: 'Choose a PDF, DOCX or text file.' }
  if (file.size > MAX_UPLOAD) return { error: 'That file is larger than 4 MB. Paste the text instead.' }
  try {
    const res = await fetch(`${API_URL}/api/extract`, {
      method: 'POST',
      headers: { 'X-Filename': encodeURIComponent(file.name) },
      body: await file.arrayBuffer(),
      cache: 'no-store',
    })
    const body = await res.json()
    if (!res.ok) return { error: typeof body.detail === 'string' ? body.detail : `The reader answered ${res.status}.` }
    return { ...body, name: file.name }
  } catch {
    return { error: 'The reader is unreachable. Try again in a moment.' }
  }
}
