// Display-only tidying. The stored text is never changed: the embeddings, the citation offsets and the filing
// checker all depend on it, so every function here takes stored text and returns what the page shows.

/** Whitespace left by HTML extraction: 'Act ( Cap. 245 )' -> 'Act (Cap. 245)', 'Act No. 10 of 1969 , Sch.' -> '…1969, Sch.'.
 * Removes spaces only, so it is safe on the courts' words too. */
export function tidySpaces(s: string) {
  return s
    .replace(/\s+/g, ' ')
    .replace(/\(\s+/g, '(')
    .replace(/\s+\)/g, ')')
    .replace(/(\S)\s+([,;:.])(?=\s|$|\))/g, '$1$2')
    .trim()
}

export interface Clause {
  level: 0 | 1 | 2 | 3 // 0: lead-in text; 1: (1); 2: (a); 3: (i)
  label: string | null
  text: string
}

const ROMAN = /^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)$/
// an amendment note inserted by the reviser: '[Act No. 5 of 2003, s. 2.]', '[L.N. 22/1999]'
const NOTE = /\[([^[\]]{3,240})\]/g
const IS_NOTE = /\b(Act|L\.N\.|No\.|Deleted|Repealed|Inserted|Sch\.|Rev\.|Cap\.)/

/** A section's flattened text split back into its subsections, paragraphs and sub-paragraphs, with the reviser's
 * amendment notes pulled out. A label only starts a new clause after punctuation ('…offence. (2) A person'), so
 * cross-references like 'section 5(1)(a)' stay inline. */
export function structure(stored: string): { clauses: Clause[]; notes: string[] } {
  const notes: string[] = []
  let text = tidySpaces(stored).replace(NOTE, (m, inner: string) => {
    if (!IS_NOTE.test(inner)) return m
    notes.push(inner.trim())
    return ''
  })
  text = tidySpaces(text)
    .replace(/(\w)\s?[-–]\s+\(/g, '$1— (') // 'at any time- (a)': a lost em dash before a list
    .replace(/([.;:—])((?:\s+(?:and|or))?)\s+\(([0-9]+[A-Z]?|[a-z]{1,2}|[ivx]+)\)\s/g, '$1$2\n($3) ')

  const clauses: Clause[] = []
  let lastLetter = ''
  for (const line of text.split('\n')) {
    const m = line.match(/^\(([^)]+)\)\s(.*)$/)
    if (!m) {
      if (line.trim()) clauses.push({ level: 0, label: null, text: line.trim() })
      continue
    }
    const [, label, rest] = m
    let level: Clause['level']
    if (/^\d/.test(label)) level = 1
    else if (ROMAN.test(label) && !(label.length === 1 && label.charCodeAt(0) === lastLetter.charCodeAt(0) + 1)) level = 3
    else {
      level = 2
      lastLetter = label
    }
    clauses.push({ level, label: `(${label})`, text: rest.trim() })
  }
  if (!clauses.length && notes.length) clauses.push({ level: 0, label: null, text: `[${notes.shift()}]` })
  return { clauses, notes }
}

/** Case names from the metadata: shouting names become title case ('REPUBLIC v DANIEL MUSYOKA MUASYA & 2 others' ->
 * 'Republic v Daniel Musyoka Muasya & 2 others'), then the reporting tail is dropped. Short capitals (AG, DKM, EG)
 * are left alone: they are usually initials. */
export function caseName(title: string | null) {
  let t = title ?? 'Unnamed case'
  const words = t.split(' ')
  const caps = (w: string) => w.length >= 3 && /^[A-Z][A-Z’'.-]+,?$/.test(w)
  if (words.some((w, i) => caps(w) && caps(words[i + 1] ?? ''))) {
    t = words
      .map((w) => (caps(w) && w.replace(/[^A-Z]/g, '').length >= 4 ? w.toLowerCase().replace(/(^|[’'-])(\p{L})/gu, (_, a, b) => a + b.toUpperCase()) : w))
      .join(' ')
  }
  return t.replace(/\s*\(.*$/, '').replace(/\s*\[.*$/, '').split(';')[0].replace(/,$/, '').trim()
}

/** Where in the judgment. The answer key's locator can carry audit notes ('112(a); scope_text from 69'); they are
 * kept, in words a reader follows. */
export function locator(p: string | null) {
  if (!p) return null
  const [main, ...rest] = p.split(';').map((s) => s.trim())
  const see = main.match(/\(see also ([^)]+)\)/)
  const head = main.replace(/\s*\((paragraphs unnumbered|see also [^)]+)\)/g, '').trim()
  const extras = [
    ...(see ? [`see also para ${see[1]}`] : []),
    ...rest.map((r) => r.replace(/^scope_text from (.+)$/, 'limiting words at para $1')),
  ]
  const where = /^\d/.test(head) ? `para ${head}` : head.charAt(0).toLowerCase() + head.slice(1)
  return extras.length ? `${where} (${extras.join('; ')})` : where
}

/** Kenya Law links sometimes carry tracking parameters from the PDF footer. */
export function cleanUrl(u: string | null) {
  if (!u) return null
  try {
    const url = new URL(u)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
    for (const k of [...url.searchParams.keys()]) if (k.startsWith('utm_')) url.searchParams.delete(k)
    return url.toString()
  } catch {
    return u
  }
}

/** The API cuts snippets at 240 characters; end on a whole word. */
export function snippet(s: string, max = 240) {
  const t = tidySpaces(s)
  if (s.length < max) return t
  const cut = t.lastIndexOf(' ', t.length - 1)
  return (cut > 0 ? t.slice(0, cut) : t).replace(/[,;:]$/, '') + '…'
}

/** Cut text into plain runs and citation runs. The API's offsets are code points (Python), so slice by code point,
 * not by UTF-16 index. A span overlapping the previous one is left unmarked, except that of two identical spans
 * ("sections 203 and 204") the one `prefer` picks owns the run. */
export function splitAt(
  text: string,
  spans: { char_start: number; char_end: number }[],
  prefer: (i: number, kept: number) => boolean = () => false,
) {
  const cps = Array.from(text)
  const out: { text: string; span: number | null }[] = []
  let at = 0
  spans.forEach((s, i) => {
    const last = out[out.length - 1]
    if (last?.span != null && spans[last.span].char_start === s.char_start && spans[last.span].char_end === s.char_end) {
      if (prefer(i, last.span)) last.span = i
      return
    }
    if (s.char_start < at) return
    out.push({ text: cps.slice(at, s.char_start).join(''), span: null })
    out.push({ text: cps.slice(s.char_start, s.char_end).join(''), span: i })
    at = s.char_end
  })
  out.push({ text: cps.slice(at).join(''), span: null })
  return out
}

export interface DiffOp {
  word: string
  op: 'same' | 'del' | 'add' // del: only in the filing's quote; add: the court's words the filing left out
}

/** Word-level diff of a filing's quote (a) against the judgment's words (b), for showing a misquote the way a copy
 * editor marks it. Case and punctuation are ignored when comparing; words are shown as the court wrote them. */
export function wordDiff(a: string, b: string): DiffOp[] {
  const A = a.split(/\s+/).filter(Boolean)
  const B = b.split(/\s+/).filter(Boolean)
  const key = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
  const L = Array.from({ length: A.length + 1 }, () => new Array<number>(B.length + 1).fill(0))
  for (let i = A.length - 1; i >= 0; i--)
    for (let j = B.length - 1; j >= 0; j--) L[i][j] = key(A[i]) === key(B[j]) ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1])
  const out: DiffOp[] = []
  let i = 0
  let j = 0
  while (i < A.length && j < B.length) {
    if (key(A[i]) === key(B[j])) {
      out.push({ word: B[j], op: 'same' })
      i++
      j++
    } else if (L[i + 1][j] >= L[i][j + 1]) out.push({ word: A[i++], op: 'del' })
    else out.push({ word: B[j++], op: 'add' })
  }
  while (i < A.length) out.push({ word: A[i++], op: 'del' })
  while (j < B.length) out.push({ word: B[j++], op: 'add' })
  return out
}
