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
