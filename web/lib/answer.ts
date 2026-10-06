// The /api/chat stream (.superpowers/sdd/2026-10-06-chat/contract.md) and how the answer's parts are laid out.

export type Ruling = {
  kind: 'ruling'
  event_id: number
  quote: string
  case: string | null
  citation: string | null
  court: string | null
  paragraph: string | null
  checked_by: string
  state: string | null
  url: string | null
}
export type SectionRef = { kind: 'section'; provision_id: string; act: string; number: string | null; heading: string | null; status: string }
export type CaseRef = { kind: 'case'; judgment_id: string; title: string; citation: string | null; url: string | null }
export type Part = { kind: 'text'; text: string } | Ruling | SectionRef | CaseRef | { kind: 'removed' }
/** Draft mode: what the filing checker still flags in the draft after one revision (empty when clean). */
export type CheckFlag = { raw_text: string; kind: 'case' | 'section' | 'quote'; result: string; note: string }
export type Answer = { text: string; parts: Part[]; removed: number; check?: CheckFlag[]; label?: string }
export type Step = { tool: string; label: string }
export type ChatEvent =
  | ({ type: 'step' } & Step)
  | ({ type: 'answer' } & Answer)
  | { type: 'done'; disclaimer: string }
  | { type: 'error'; message: string }

export type Inline = string | SectionRef | CaseRef | { kind: 'removed' }
export type TextLine = { bullet: boolean; items: Inline[] }
export type Line = TextLine | { ruling: Ruling }

const BULLET = /^\s*[-*]\s+/

/** Parts -> lines. A newline inside a text part starts a new line (a bullet if it starts "- " or "* "); references
 * stay inline in the line they fall in; a ruling is a block of its own. */
export function toLines(parts: Part[]): Line[] {
  const lines: Line[] = []
  let cur = null as TextLine | null
  const start = (chunk: string) => {
    const m = chunk.match(BULLET)
    cur = { bullet: !!m, items: [] }
    lines.push(cur)
    return m ? chunk.slice(m[0].length) : chunk
  }
  for (const p of parts) {
    if (p.kind === 'text') {
      p.text.split('\n').forEach((chunk, k) => {
        if (k > 0 || !cur) chunk = start(chunk)
        if (chunk) cur!.items.push(chunk)
      })
    } else if (p.kind === 'ruling') {
      lines.push({ ruling: p })
      cur = null
    } else {
      if (!cur) start('')
      cur!.items.push(p)
    }
  }
  return lines
}

/** A line with nothing but whitespace: a paragraph break. */
export const isBlank = (l: Line) => !('ruling' in l) && l.items.every((x) => typeof x === 'string' && !x.trim())
