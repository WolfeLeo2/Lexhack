// Forwards a question to the API's /api/chat and streams the NDJSON answer straight back (contract:
// .superpowers/sdd/2026-10-06-chat/contract.md). Server to server, so no CORS.
import { API_URL } from '@/lib/api'

export const maxDuration = 60 // Vercel: the agent takes a few tool calls

const MESSAGES: Record<number, string> = {
  413: 'That question is too long. Shorten it and ask again.',
  422: 'That question could not be read. Rephrase it and ask again.',
  429: 'That is a lot of questions in one minute. Wait a moment, then ask again.',
}

export async function POST(req: Request) {
  let upstream: Response
  try {
    upstream = await fetch(`${API_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: await req.text(),
      cache: 'no-store',
    })
  } catch {
    return Response.json({ error: 'Hakiki’s service is unreachable. Try again in a moment.' }, { status: 502 })
  }
  if (upstream.ok && upstream.body)
    return new Response(upstream.body, { headers: { 'Content-Type': 'application/x-ndjson', 'Cache-Control': 'no-store' } })
  const known = upstream.status in MESSAGES
  return Response.json(
    { error: MESSAGES[upstream.status] ?? 'Hakiki’s service could not answer just now. Try again in a moment.' },
    { status: known ? upstream.status : 502 },
  )
}
