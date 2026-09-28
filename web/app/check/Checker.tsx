'use client'
import Link from 'next/link'
import { useActionState, useState } from 'react'
import type { CaseCheck, Finding, QuoteCheck, SectionCheck } from '@/lib/api'
import { CheckedTag, UnverifiedTag } from '@/components/court'
import { cap, courtActed, sectionHref } from '@/lib/format'
import { splitAt } from '@/lib/text'
import { checkFiling, type CheckState } from './actions'

const DEMOS = [
  ['clean', 'Sound citations'],
  ['hallucinated', 'Invented and misquoted'],
  ['stale_law', 'Relies on struck-down law'],
] as const

/** A finding worth a second look: a case we can't match, words not found as quoted, or a section a court acted on. */
function needsLook(f: Finding) {
  if (f.case) return f.case.result !== 'found' || f.quotes.some((q) => q.result === 'close' || q.result === 'not_found')
  return !!f.section?.status && courtActed(f.section.status)
}

export function Checker() {
  const [state, action, pending] = useActionState<CheckState, FormData>(checkFiling, { text: '', report: null, error: null })
  const [text, setText] = useState('')

  async function loadDemo(name: string) {
    setText(await (await fetch(`/demo/${name}.txt`)).text())
  }

  return (
    <div className="mt-8">
      <form action={action}>
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2 text-sm text-ink-2">
          <span>Try a synthetic filing:</span>
          {DEMOS.map(([name, label]) => (
            <button key={name} type="button" onClick={() => loadDemo(name)} className="underline decoration-rule underline-offset-4 hover:text-ink">
              {label}
            </button>
          ))}
        </div>
        <label htmlFor="filing" className="sr-only">
          Filing text
        </label>
        <textarea
          id="filing"
          name="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={14}
          placeholder="Paste a submission, pleading or judgment."
          className="statute mt-3 w-full rounded-sm border border-rule bg-paper p-4 text-[1.02rem] leading-relaxed focus:border-ink focus:outline-none"
        />
        <button type="submit" disabled={pending} className="mt-3 rounded-sm bg-ink px-5 py-2 text-paper disabled:opacity-60">
          {pending ? 'Checking…' : 'Check citations'}
        </button>
        {state.error && (
          <p className="mt-3 text-seal" role="alert">
            {state.error}
          </p>
        )}
      </form>
      {state.report && <Report text={state.text} findings={state.report.findings} disclaimer={state.report.disclaimer} />}
    </div>
  )
}

function Report({ text, findings, disclaimer }: { text: string; findings: Finding[]; disclaimer: string }) {
  const flagged = findings.filter(needsLook).length
  return (
    <section className="mt-12" aria-labelledby="report">
      <h2 id="report" className="statute text-2xl">
        {findings.length ? `${findings.length} citations found; ${flagged} worth a second look` : 'No citations Hakiki can check'}
      </h2>
      {!findings.length && (
        <p className="mt-2 max-w-[68ch] text-ink-2">
          Hakiki reads neutral citations such as [2017] KESC 2 (KLR) and sections of the Acts it holds. Citations in the older [2017] eKLR form are not read yet, so
          this is not a sign the filing is sound.
        </p>
      )}
      <p className="mt-2 text-sm text-ink-2">{disclaimer}</p>
      {findings.length > 0 && (
        <div className="mt-6 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="statute max-h-[70vh] overflow-y-auto whitespace-pre-wrap rounded-sm border border-rule p-5 leading-relaxed">
            {splitAt(text, findings, (i, kept) => needsLook(findings[i]) && !needsLook(findings[kept])).map((p, i) =>
              p.span === null ? (
                <span key={i}>{p.text}</span>
              ) : (
                <a key={i} href={`#f${p.span}`} className={needsLook(findings[p.span]) ? 'bg-seal/15 text-seal underline' : 'bg-panel underline decoration-rule'}>
                  {p.text}
                </a>
              ),
            )}
          </div>
          <ol className="divide-y divide-rule border-y border-rule">
            {findings.map((f, i) => (
              <li key={i} id={`f${i}`} className="py-5">
                <p className="statute text-lg">{f.raw_text}</p>
                {f.case && <CaseLine c={f.case} />}
                {f.quotes.map((q, j) => (
                  <QuoteLine key={j} q={q} />
                ))}
                {f.section && <SectionLine s={f.section} />}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}

function CaseLine({ c }: { c: CaseCheck }) {
  const j = c.judgment
  if (c.result === 'not_in_collection')
    return (
      <p className="mt-1 text-ink-2">
        Not in our collection. We hold about 10% of published Kenyan judgments, so this does not show the case doesn’t exist; check it on Kenya Law.
      </p>
    )
  return (
    <p className={`mt-1 ${c.result === 'name_mismatch' ? 'text-seal' : 'text-ink-2'}`}>
      {c.result === 'name_mismatch' ? `This citation belongs to a different case in our collection. The filing calls it “${c.cited_name}”; the citation is ` : 'In our collection: '}
      {j?.source_url ? (
        <a href={j.source_url} className="underline" target="_blank" rel="noreferrer">
          {j.title}
        </a>
      ) : (
        j?.title
      )}
      .
    </p>
  )
}

const QUOTE_LABEL: Record<QuoteCheck['result'], string> = {
  verbatim: 'Quoted words appear word for word in the judgment',
  close: 'Quoted words are close to the judgment but not word for word',
  not_found: 'Quoted words were not found in the judgment',
  not_checked: 'Quoted words not checked: we don’t hold this judgment’s text',
}

function QuoteLine({ q }: { q: QuoteCheck }) {
  const off = q.result === 'close' || q.result === 'not_found'
  return (
    <div className="mt-3 border-l-2 border-rule pl-3">
      <p className={off ? 'text-seal' : 'text-ink-2'}>
        {QUOTE_LABEL[q.result]}
        {q.result === 'close' && q.similarity !== null && ` (${Math.round(q.similarity * 100)}% similar)`}
        {q.paragraph && `, paragraph ${q.paragraph}`}.
      </p>
      <p className="statute mt-1 text-ink-2">Filing: “{q.quote}”</p>
      {off && q.court_text && (
        <p className="statute mt-1">
          {q.result === 'close' ? 'The court wrote' : 'Nearest passage'}: “{q.court_text}”
        </p>
      )}
    </div>
  )
}

function SectionLine({ s }: { s: SectionCheck }) {
  if (s.result === 'not_covered' || !s.provision) return <p className="mt-1 text-ink-2">{s.act_ref ? `${s.act_ref}: not` : 'Not'} a section Hakiki covers yet.</p>
  const p = s.provision
  return (
    <div className="mt-1">
      <p className={s.status && courtActed(s.status) ? 'text-seal' : 'text-ink-2'}>
        <Link href={sectionHref(p.provision_id)} className="underline">
          {p.act_title}, s.{p.number}
        </Link>
        : {cap(s.status ?? '')}.
      </p>
      {s.summary_events.map((e) => (
        <blockquote key={e.event_id} className="statute mt-2 border-l-2 border-seal/60 pl-3">
          “{e.operative_quote}”
          <footer className="mt-1 text-sm text-ink-2">
            {e.source_url ? (
              <a href={e.source_url} className="underline" target="_blank" rel="noreferrer">
                {e.title}
              </a>
            ) : (
              e.title
            )}
            {e.source_paragraph && `, para ${e.source_paragraph}`}
            <span className="ml-2">{e.verified ? <CheckedTag by={e.verified_by} /> : <UnverifiedTag />}</span>
          </footer>
        </blockquote>
      ))}
    </div>
  )
}
