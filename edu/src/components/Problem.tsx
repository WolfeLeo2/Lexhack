import { Ban, FileSearch, Quote } from 'lucide-react'
import { PROVISIONS } from '../lib/data.ts'
import { CourtWords, Part, fmtDate, shortCase } from './ui.tsx'

const EXAMPLES = ['204', '194', '29']

export function Problem() {
  const rows = EXAMPLES.map((n) => PROVISIONS.find((p) => p.provision.number === n && p.history.length)!)
  return (
    <Part
      id="problem"
      n={1}
      title="The problem"
      lede={
        <>
          <p>
            Kenya Law publishes the official text of every Act, kept up to date when Parliament changes it. When a
            court strikes a section down, though, the text stays exactly as it was. Of the 1,038 editorial notes on the
            statute pages we collected, not one mentions a court decision. They are all amendment history.
          </p>
          <p>
            Here are three sections as Kenya Law prints them, next to what a court said about each. Nothing on the
            statute page tells you about the right-hand column.
          </p>
        </>
      }
    >
      <div className="divide-y divide-rule border-y border-rule">
        {rows.map(({ provision: p, summary_events: [e] }) => (
          <article key={p.provision_id} className="grid grid-cols-1 gap-6 py-8 md:grid-cols-2 md:gap-10">
            <div>
              <p className="text-sm text-ink-2">
                What Kenya Law prints ({p.act_title}, version of {fmtDate(p.version_date)})
              </p>
              <p className="statute mt-2 line-clamp-5 text-[1.1rem]">{p.text}</p>
            </div>
            <div className="md:border-l md:border-rule md:pl-10">
              <p className="text-sm text-seal">
                {e.court}, {fmtDate(e.effective_date)}: {shortCase(e)}
              </p>
              <CourtWords quote={e.operative_quote} mark={e.scope_text} className="mt-2 text-[1.05rem]" />
            </div>
          </article>
        ))}
      </div>

      <div className="mt-14 grid grid-cols-1 gap-10 md:grid-cols-3">
        <div>
          <FileSearch className="text-gazette" aria-hidden />
          <h3 className="mt-3 font-semibold">Who gets it wrong</h3>
          <p className="mt-2 text-ink-2">
            Anyone who trusts the official text: a student revising, a lawyer drafting a charge, a magistrate in a busy
            court, and AI tools, which learn from that same text and then cite it confidently.
          </p>
        </div>
        <div>
          <Quote className="text-gazette" aria-hidden />
          <h3 className="mt-3 font-semibold">What LexHack does</h3>
          <p className="mt-2 text-ink-2">
            For any section it shows where it stands today, the court's exact words and a link to the judgment. The US
            has tools like this (Shepard's, KeyCite), called citators. Kenya has none. A filing checker sits on top: it
            reads a legal document and flags fake cases, misquotes and struck-down sections.
          </p>
        </div>
        <div>
          <Ban className="text-gazette" aria-hidden />
          <h3 className="mt-3 font-semibold">What it doesn't do</h3>
          <p className="mt-2 text-ink-2">
            It never gives legal advice, and it never says whether a case supports someone's argument. It reports what
            published sources say, with the source, and leaves the judgment to the reader.
          </p>
        </div>
      </div>
    </Part>
  )
}
