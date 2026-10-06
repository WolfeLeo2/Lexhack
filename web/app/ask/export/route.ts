// Forwards an answer or draft to the API's /api/export and passes the Word or PDF file back. The API rebuilds every
// court quote and section status from its database; this only relays. Server to server, so no CORS.
import { API_URL } from '@/lib/api'

const MESSAGES: Record<number, string> = {
  413: 'That answer is too large to download. Copy the text instead.',
  422: 'That answer could not be turned into a file.',
  429: 'That is a lot of downloads in one minute. Wait a moment, then try again.',
}

export async function POST(req: Request) {
  // Rate limits are per user; the API trusts the client IP we forward only with the shared secret (server-only).
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const secret = process.env.CHAT_PROXY_SECRET
  if (secret) {
    headers['x-hakiki-proxy-key'] = secret
    headers['x-hakiki-client-ip'] = req.headers.get('x-real-ip') ?? req.headers.get('x-forwarded-for')?.split(',')[0].trim() ?? ''
  }
  let upstream: Response
  try {
    upstream = await fetch(`${API_URL}/api/export`, { method: 'POST', headers, body: await req.text(), cache: 'no-store' })
  } catch {
    return Response.json({ error: 'Hakiki’s service is unreachable. Try again in a moment.' }, { status: 502 })
  }
  if (upstream.ok)
    return new Response(upstream.body, {
      headers: {
        'Content-Type': upstream.headers.get('Content-Type') ?? 'application/octet-stream',
        'Content-Disposition': upstream.headers.get('Content-Disposition') ?? 'attachment',
        'Cache-Control': 'no-store',
      },
    })
  const known = upstream.status in MESSAGES
  return Response.json(
    { error: MESSAGES[upstream.status] ?? 'Hakiki couldn’t make the file just now. Try again in a moment.' },
    { status: known ? upstream.status : 502 },
  )
}
