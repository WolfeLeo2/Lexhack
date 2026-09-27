// The filing checker's three checks, run in the browser against the demo data:
//   1. does the cited case exist?  2. is the quoted passage in it?  3. is the cited section still good law?
// The real checker will run the same checks against the database through the API.
import type { CourtEvent, Judgment, Provision, ProvisionStatus } from './types.ts'

const ACTS: [RegExp, string][] = [
  [/^penal code$/i, 'ke/act/cap-63'],
  [/^(sexual offences act|soa)$/i, 'ke/act/cap-63a'],
  [/^(kenya information and communications? act|kica)$/i, 'ke/act/cap-411a'],
]
const SECTION =
  /\b(?:[Ss]ections?|s\.)\s*(\d+[A-Z]?)((?:\s*\([0-9a-z]+\))*)\s+of\s+the\s+((?:(?:[A-Z][A-Za-z'-]*|and|of)\s+)*?(?:Code|Act)\b|KICA|SOA)/g
const CASE = /\[(\d{4})\]\s*(?:eKLR|(KESC|KECA|KEHC)\s+(\d+))(?:\s*\(KLR\))?/g
const QUOTE = /[“"]([^”"]{12,})[”"]/

export type DiffToken = { w: string; kind: 'same' | 'added' | 'missing' }

export type SectionFinding = {
  kind: 'section'
  start: number
  end: number
  raw: string
  actName: string
  actId: string | null
  number: string
  subsection: string
  result: ProvisionStatus | null
}

export type CaseFinding = {
  kind: 'case'
  start: number
  end: number
  raw: string
  name: string
  judgment: Judgment | null
  rulings: { provision: Provision; event: CourtEvent }[]   // what this judgment did to sections, and whether it still stands
  quote: null | {
    text: string
    start: number
    end: number
    verbatim: boolean
    closest: string | null
    diff: DiffToken[]
  }
}

export type Finding = SectionFinding | CaseFinding

export const norm = (s: string) =>
  s
    .toLowerCase()
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/\s+/g, ' ')
    .replace(/[\s.,;:]+$/, '')
    .trim()

const words = (s: string) => s.split(/\s+/).filter(Boolean)

/** Word-level diff of what a filing quotes against what the judgment says, trimmed to the overlapping part. */
export function diffWords(quoted: string, source: string): DiffToken[] {
  const a = words(quoted)
  const b = words(source)
  const key = (w: string) => norm(w).replace(/[^\p{L}\p{N}]/gu, '')
  const L = Array.from({ length: a.length + 1 }, () => Array.from<number>({ length: b.length + 1 }).fill(0))
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      L[i][j] = key(a[i]) === key(b[j]) ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1])
  const out: DiffToken[] = []
  let i = 0
  let j = 0
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && key(a[i]) === key(b[j])) {
      out.push({ w: b[j++], kind: 'same' })
      i++
    } else if (j < b.length && (i === a.length || L[i][j + 1] >= L[i + 1][j])) out.push({ w: b[j++], kind: 'missing' })
    else out.push({ w: a[i++], kind: 'added' })
  }
  // keep the judgment's words only where they overlap the quote; the filing's added words are always kept
  const first = out.findIndex((t) => t.kind === 'same')
  const last = out.findLastIndex((t) => t.kind === 'same')
  return out.filter((t, k) => t.kind !== 'missing' || (k > first && k < last))
}

function overlap(a: string, b: string) {
  const A = new Set(words(norm(a)))
  const B = new Set(words(norm(b)))
  let n = 0
  A.forEach((w) => B.has(w) && n++)
  return n / Math.max(1, Math.min(A.size, B.size))
}

/** The case name just before a citation: "X v Y", where each party is a run of capitalised words (and "&",
 *  "another", "2 others"…), so lead-in words like "The Prosecution relies on" are left out. */
function caseName(before: string) {
  const party = (w: string) => /^[A-Z(]/.test(w) || /^(&|and|another|others|of|\d+)$/.test(w)
  const toks = before.trimEnd().split(/\s+/)
  const v = toks.map((t) => t.replace(/[,;:]$/, '')).lastIndexOf('v')
  if (v < 1) return toks.slice(-4).join(' ')
  let i = v - 1
  while (i > 0 && party(toks[i - 1])) i--
  while (i < v - 1 && !/^[A-Z]/.test(toks[i])) i++
  return toks.slice(i).join(' ')
}

function findJudgment(index: Judgment[], year: string, court: string | undefined, num: string | undefined, name: string) {
  if (court && num) return index.find((j) => j.judgment_id === `ke/judgment/${court.toLowerCase()}/${year}/${num}`) ?? null
  // eKLR citations carry no court or number: match the year plus any party name
  const parties = words(name.replace(/[^\p{L}\s]/gu, ' ')).filter(
    (w) => /^[A-Z][a-z]{2,}/.test(w) && !/^(Republic|Attorney|General|The|Another|Others|Hon)$/.test(w),
  )
  return (
    index.find((j) => {
      const hay = ` ${j.title} ${j.alt_citation ?? ''} `.toLowerCase()
      return j.decision_date.startsWith(year) && parties.some((w) => hay.includes(` ${w.toLowerCase()} `))
    }) ?? null
  )
}

export function check(text: string, provisions: ProvisionStatus[], index: Judgment[]): Finding[] {
  const found: Finding[] = []
  for (const m of text.matchAll(SECTION)) {
    const actName = m[3].replace(/\s+/g, ' ')
    const actId = ACTS.find(([re]) => re.test(actName))?.[1] ?? null
    const result =
      provisions.find((p) => p.provision.act_id === actId && p.provision.number === m[1]) ?? null
    found.push({
      kind: 'section', start: m.index, end: m.index + m[0].length, raw: m[0], actName, actId,
      number: m[1], subsection: m[2].replace(/\s+/g, ''), result,
    })
  }
  const cases = [...text.matchAll(CASE)]
  cases.forEach((m, k) => {
    const lineStart = Math.max(text.lastIndexOf('\n', m.index), m.index - 160)
    const name = caseName(text.slice(Math.max(0, lineStart), m.index))
    const start = m.index - name.length - (text.slice(0, m.index).endsWith(' ') ? 1 : 0)
    const end = m.index + m[0].length
    const judgment = findJudgment(index, m[1], m[2], m[3], name)
    // a quotation belongs to the case cited just before it, up to the next case citation
    const until = k + 1 < cases.length ? cases[k + 1].index : text.length
    const after = text.slice(end, Math.min(until, end + 420))
    const q = after.match(QUOTE)
    let quote: CaseFinding['quote'] = null
    if (q && q.index != null) {
      const passages = judgment?.passages ?? []
      const verbatim = passages.some((p) => norm(p).includes(norm(q[1])))
      const closest = verbatim
        ? null
        : passages.reduce<string | null>(
            (best, p) => (overlap(q[1], p) > (best ? overlap(q[1], best) : 0.3) ? p : best),
            null,
          )
      quote = {
        text: q[1], start: end + q.index, end: end + q.index + q[0].length, verbatim, closest,
        diff: closest ? diffWords(q[1], closest) : [],
      }
    }
    const rulings = judgment
      ? provisions.flatMap((p) =>
          p.history.filter((e) => e.source_url === judgment.source_url).map((event) => ({ provision: p.provision, event })),
        )
      : []
    found.push({
      kind: 'case', start: Math.max(0, start), end, raw: text.slice(Math.max(0, start), end), name, judgment, rulings, quote,
    })
  })
  return found.sort((a, b) => a.start - b.start)
}
