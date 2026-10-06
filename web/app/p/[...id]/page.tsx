import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { Citations } from '@/components/Citations'
import { Attribution, CheckedTag, CourtWords, EventEntry, UnverifiedTag } from '@/components/court'
import { BlankPage } from '@/components/illustrations'
import { Lineage } from '@/components/Lineage'
import { StatusStamp } from '@/components/Stamp'
import { StatuteText } from '@/components/StatuteText'
import { getCitations, getProvision } from '@/lib/api'
import { EVENT_LABEL, actHref, courtActed, fmtDate, isStatutory, plural, sectionHref, stripHead } from '@/lib/format'
import { cleanUrl } from '@/lib/text'

type Props = PageProps<'/p/[...id]'>

const CITES = 10

async function load({ params, searchParams }: Props) {
  const id = (await params).id.map(decodeURIComponent).join('/')
  const sp = await searchParams
  const leads = sp.leads === '1'
  const cites = Math.min(100, Math.max(CITES, Number(sp.cites) || CITES))
  const [data, citing] = await Promise.all([getProvision(id, leads), getCitations(id, cites)])
  return { id, leads, cites, data, citing }
}

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { data } = await load(props)
  if (!data) return {}
  const p = data.provision
  return { title: `${p.act_title} s.${p.number}`, description: `${p.heading}: ${data.status}.` }
}

export default async function ProvisionPage(props: Props) {
  const { id, leads, cites, data, citing } = await load(props)
  if (!data) notFound()
  const { provision: p, status, summary_events: summary, cited_by, lead_count } = data
  const acted = courtActed(status)
  // Parliament's changes get their own list: decades of amendments would crowd out the courts' lineage
  const history = data.history.filter((e) => !isStatutory(e))
  const parliament = data.history.filter(isStatutory)
  const query = (o: { leads?: boolean; cites?: number }) => {
    const q = new URLSearchParams()
    if (o.leads ?? leads) q.set('leads', '1')
    if ((o.cites ?? cites) > CITES) q.set('cites', String(o.cites ?? cites))
    return `/p/${id}${q.size ? `?${q}` : ''}`
  }
  const srcUrl = cleanUrl(p.source_url)
  const from = data.renumbered_from
  const to = data.renumbered_to
  const eid = (pid: string) => pid.split('/').pop()
  const onOld = from && data.history.some((e) => !isStatutory(e) && e.provision_id === from.provision_id)

  return (
    <article className="pt-8">
      <nav aria-label="Breadcrumb" className="text-[0.95rem] text-ink-2">
        <Link href="/acts" className="hover:text-ink">
          Acts
        </Link>
        <span aria-hidden> / </span>
        <Link href={actHref(p.act_id)} className="hover:text-ink">
          {p.act_title}
        </Link>
        <span aria-hidden> / </span>
        <span aria-current="page">Section {p.number}</span>
      </nav>

      <div className="mt-8 grid grid-cols-1 gap-x-14 gap-y-10 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div>
          <p className="statute text-lg text-ink-2">
            {p.act_title}, section {p.number}
          </p>
          <h1 className="statute mt-1 text-[2.5rem] leading-[1.1] font-medium tracking-[-0.015em] sm:text-[3.2rem]">
            {p.heading ?? `Section ${p.number}`}
          </h1>
          <StatuteText text={stripHead(p.text, p.number, p.heading)} number={p.number} />
          <p className="mt-3 text-sm text-ink-2">
            Text as published by Kenya Law, version of {fmtDate(p.version_date)}.{' '}
            {srcUrl && (
              <a href={srcUrl} className="link" target="_blank" rel="noreferrer">
                See this version on Kenya Law
              </a>
            )}
            {acted && '. The published text carries no note of the court rulings on this page.'}
          </p>
        </div>

        <aside className="lg:pt-16" aria-label="Status">
          <StatusStamp status={status} />
          {(from || to) && (
            <p className="mt-4 text-[0.95rem] text-ink-2">
              {to ? (
                <>
                  Kenya Law renumbered this section from the version of {fmtDate(to.versions[0])}: it is now{' '}
                  <Link href={sectionHref(to.provision_id)} className="link">
                    <code className="text-[0.9em]">{eid(to.provision_id)}</code>
                  </Link>
                  . The status and rulings here cover both numberings.
                </>
              ) : (
                from && (
                  <>
                    Up to Kenya Law’s version of {fmtDate(from.versions.at(-1) ?? null)} this section was{' '}
                    <Link href={sectionHref(from.provision_id)} className="link">
                      <code className="text-[0.9em]">{eid(from.provision_id)}</code>
                    </Link>
                    .{onOld && ' The court rulings below were made on that numbering.'}
                  </>
                )
              )}
            </p>
          )}
          {status === 'repealed' ? (
            <div className="mt-6 space-y-2 text-[0.95rem] text-ink-2">
              {summary.filter(isStatutory).map((e) => (
                <p key={e.event_id}>
                  Parliament repealed this section ({e.source_paragraph?.replace(/\.$/, '')}). Kenya Law’s note reads{' '}
                  <span className="statute text-ink">{e.operative_quote}</span>
                </p>
              ))}
            </div>
          ) : summary.length > 0 ? (
            <div className="mt-6 space-y-6">
              <p className="text-[0.95rem] text-ink-2">
                {summary.length === 1 ? 'Because of this ruling:' : 'Because of these rulings, read together:'}
              </p>
              {summary.map((e) => (
                <div key={e.event_id} className="space-y-2">
                  <CourtWords quote={e.scope_text ?? e.operative_quote} className="text-[1.05rem]" />
                  <Attribution e={e} />
                  {e.verified ? <CheckedTag by={e.verified_by} /> : <UnverifiedTag />}
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-6 space-y-3 text-[0.95rem] text-ink-2">
              <p>
                {cited_by > 0
                  ? `Cited in ${plural(cited_by, 'judgment')} we hold. None of the rulings checked so far limits, upholds or strikes it down.`
                  : 'No judgment we hold cites this section.'}
              </p>
              {lead_count > 0 && !leads && (
                <p>
                  Our pipeline found {plural(lead_count, 'possible ruling')} on it that no reviewer has checked yet.{' '}
                  <Link href={query({ leads: true })} scroll={false} className="link">
                    Show {lead_count === 1 ? 'it' : 'them'}
                  </Link>
                </p>
              )}
              <p>
                The Internet Archive holds about a tenth of Kenyan judgments, so this is not proof that no court has
                ruled on it.
              </p>
            </div>
          )}
        </aside>
      </div>

      <section className="mt-16 border-t border-rule pt-10" aria-labelledby="history-h">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 id="history-h" className="statute text-[2rem] font-medium tracking-[-0.01em]">
            What the courts have done
          </h2>
          {(lead_count > 0 || leads) && (
            <Link
              href={query({ leads: !leads })}
              scroll={false}
              className="text-[0.95rem] text-ink-2 underline decoration-rule underline-offset-4 hover:text-ink"
            >
              {leads ? 'Hide unverified leads' : `Show ${plural(lead_count, 'unverified lead')}`}
            </Link>
          )}
        </div>
        {leads && (
          <p className="mt-3 max-w-[68ch] text-[0.95rem] text-ink-2">
            Leads are rulings our pipeline found in judgment text that no reviewer has checked yet. In a blind review about
            four in five were right. They are drawn with a dashed line and never change the status above.
          </p>
        )}

        {history.length > 0 ? (
          <>
            <div className="mt-8 max-w-4xl">
              <Lineage events={history} />
            </div>
            <ol className="mt-10 max-w-[74ch] space-y-10">
              {history.map((e) => (
                <EventEntry key={e.event_id} e={e} all={history} />
              ))}
            </ol>
          </>
        ) : (
          <div className="mt-8 flex max-w-[60ch] items-center gap-6 text-ink-2">
            <BlankPage className="h-28 w-24 shrink-0" />
            <p>
              No checked rulings yet. When a court limits, upholds or strikes down this section, its words will appear
              here, quoted exactly, with a link to the judgment.
            </p>
          </div>
        )}
      </section>

      {parliament.length > 0 && (
        <section className="mt-16 border-t border-rule pt-10" aria-labelledby="parl-h">
          <h2 id="parl-h" className="statute text-[2rem] font-medium tracking-[-0.01em]">
            What Parliament has done
          </h2>
          <p className="mt-2 max-w-[68ch] text-ink-2">
            From the reviser’s notes in Kenya Law’s own text. The notes give only the year of the amending law, not the
            day it took effect.
          </p>
          <ol className="mt-6 max-w-[74ch] divide-y divide-rule border-y border-rule">
            {parliament.map((e) => (
              <li key={e.event_id} className="grid grid-cols-[3.5rem_minmax(0,1fr)] gap-x-4 py-3">
                <span className="statute text-lg text-ink-2 tabular-nums">{e.effective_date?.slice(0, 4)}</span>
                <span>
                  <span className="statute text-lg">
                    {EVENT_LABEL[e.event_type]}
                    {e.subsection && <span className="text-ink-2"> (s.{e.subsection})</span>}
                  </span>
                  <span className="block text-[0.95rem] text-ink-2">{e.source_paragraph}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {citing && citing.total > 0 && (
        <section className="mt-16 border-t border-rule pt-10" aria-labelledby="cited-h">
          <h2 id="cited-h" className="statute text-[2rem] font-medium tracking-[-0.01em]">
            Judgments that cite it
          </h2>
          <p className="mt-2 max-w-[68ch] text-ink-2">
            {plural(citing.total, 'judgment')} we hold mention this section, highest court first, then newest. Citing a
            section is not ruling on it: most of these simply apply it to the case in front of the court.
          </p>
          <Citations total={citing.total} judgments={citing.judgments} more={cites < 100 ? query({ cites: cites + 30 }) : null} />
        </section>
      )}

      <p className="mt-16 text-sm text-ink-2">{data.disclaimer}</p>
    </article>
  )
}
