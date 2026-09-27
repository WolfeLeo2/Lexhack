import Link from 'next/link'
import { Shelf } from '@/components/illustrations'
import { SearchBox } from '@/components/SearchBox'
import { SectionMeta } from '@/components/SectionMeta'
import { type Example, Specimen } from '@/components/Specimen'
import { getActs, getProvision, getSections, getStats } from '@/lib/api'
import { courtActed, fmtDate, plural, sectionHref, shortCase, stripHead } from '@/lib/format'
import { tidySpaces } from '@/lib/text'

// The three anchor rulings (CLAUDE.md): a partial limit, a partial strike-down, and a whole section struck down.
const EXAMPLES = [
  'ke/act/cap-63/part_II__chp_XVIII__subpart_nn_1__sec_204',
  'ke/act/cap-63/part_II__chp_XVIII__sec_194',
  'ke/act/cap-411a/part_III__sec_29',
]
const FOCUS = ['ke/act/cap-63', 'ke/act/cap-63a', 'ke/act/cap-411a']
const SHORT: Record<string, string> = { 'Kenya Information and Communications Act': 'KICA' }

export default async function Home() {
  const [acts, stats, examples, ...focus] = await Promise.all([
    getActs(),
    getStats(),
    Promise.all(EXAMPLES.map((id) => getProvision(id, false))),
    ...FOCUS.map(getSections),
  ])
  const specimens: Example[] = examples.flatMap((d) => {
    const e = d?.summary_events.find((x) => x.event_type !== 'interpreted')
    if (!d || !e) return []
    const p = d.provision
    return [
      {
        href: sectionHref(p.provision_id),
        tab: `${SHORT[p.act_title] ?? p.act_title} s.${p.number}`,
        act: p.act_title,
        number: p.number ?? '',
        heading: p.heading ?? '',
        text: stripHead(p.text, p.number, p.heading),
        status: d.status,
        quote: tidySpaces(e.scope_text ?? e.operative_quote),
        court: e.court ?? 'court',
        date: fmtDate(e.effective_date),
        caseName: shortCase(e.title),
      },
    ]
  })
  const changed = focus.flatMap((s) => s ?? []).filter((s) => courtActed(s.status))

  return (
    <>
      <section className="grid grid-cols-1 gap-x-14 gap-y-12 pt-14 pb-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:pt-20">
        <div className="lg:pt-10">
          <h1 className="statute text-[2.6rem] leading-[1.08] font-medium tracking-[-0.02em] sm:text-[3.6rem]">
            Is this section still good law?
          </h1>
          <p className="mt-6 max-w-[52ch] text-lg text-ink-2">
            Kenya Law publishes the text of every Act, but not what the courts have done to it. Hakiki puts each section
            next to the rulings that limited, upheld or struck it down, in the courts’ own words.
          </p>
          <div className="mt-8 max-w-xl">
            <SearchBox />
          </div>
          <p className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-[0.95rem]">
            <Link href="/acts" className="link">
              Browse the Acts
            </Link>
            <Link href="/about" className="link">
              How to use Hakiki
            </Link>
          </p>
        </div>
        {specimens.length > 0 && <Specimen examples={specimens} />}
      </section>

      <section className="border-t border-rule pt-12" aria-labelledby="changed-h">
        <h2 id="changed-h" className="statute text-[2rem] font-medium tracking-[-0.01em]">
          Sections the courts have acted on
        </h2>
        <p className="mt-2 max-w-[64ch] text-ink-2">
          {plural(stats.verified_sections, 'section')} with checked rulings, from{' '}
          {plural(stats.judgments, 'judgment')} read. Another {plural(stats.lead_sections, 'section')} have possible
          rulings waiting for review; open an Act to see them.
        </p>
        <ul className="mt-8 divide-y divide-rule border-y border-rule">
          {changed.map((s) => (
            <li key={s.provision_id}>
              <Link
                href={sectionHref(s.provision_id)}
                className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-baseline gap-x-4 gap-y-1 py-4 hover:bg-panel/60 sm:grid-cols-[4.5rem_minmax(0,1fr)_minmax(0,20rem)]"
              >
                <span className="statute text-right text-2xl text-ink-2 tabular-nums">{s.number}</span>
                <span>
                  <span className="statute text-xl">{s.heading}</span>
                  <span className="block text-sm text-ink-2">{s.act_title}</span>
                </span>
                <span className="col-start-2 sm:col-start-3">
                  <SectionMeta {...s} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-20" aria-labelledby="shelf-h">
        <h2 id="shelf-h" className="statute text-[2rem] font-medium tracking-[-0.01em]">
          The Acts on the shelf
        </h2>
        <p className="mt-2 max-w-[62ch] text-ink-2">
          {acts.length} Acts, every version the Internet Archive kept. Open one to browse its sections.
        </p>
        <div className="mt-6">
          <Shelf acts={acts} />
        </div>
      </section>
    </>
  )
}
