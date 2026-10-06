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
  // The API limits questions per user; it trusts the client IP we forward only with the shared secret (server-only).
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const secret = process.env.CHAT_PROXY_SECRET
  if (secret) {
    headers['x-hakiki-proxy-key'] = secret
    headers['x-hakiki-client-ip'] = req.headers.get('x-real-ip') ?? req.headers.get('x-forwarded-for')?.split(',')[0].trim() ?? ''
  }
  let upstream: Response
  try {
    upstream = await fetch(`${API_URL}/api/chat`, {
      method: 'POST',
      headers,
      body: await req.text(),
      cache: 'no-store',
      signal: req.signal, // the reader left: drop the upstream stream too, so the API stops the agent
    })
  } catch {
    return Response.json({ error: 'Hakiki’s service is unreachable. Try again in a moment.' }, { status: 502 })
  }
  if (upstream.ok && upstream.body)
    return new Response(upstream.body, { headers: { 'Content-Type': 'application/x-ndjson', 'Cache-Control': 'no-store' } })
  const known = upstream.status in MESSAGES
  // A 429 is either this user's limit or Hakiki being busy for everyone; pass the API's busy message through.
  const detail = upstream.status === 429 ? String((await upstream.json().catch(() => null))?.detail ?? '') : ''
  return Response.json(
    { error: (/busy/i.test(detail) && detail + '.') || MESSAGES[upstream.status] || 'Hakiki’s service could not answer just now. Try again in a moment.' },
    { status: known ? upstream.status : 502 },
  )
}
