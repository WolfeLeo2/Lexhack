import type { Metadata } from 'next'
import Link from 'next/link'
import { Shelf } from '@/components/illustrations'
import { getActs } from '@/lib/api'
import { actHref, capLabel, fmtDate } from '@/lib/format'

export const metadata: Metadata = { title: 'Acts' }

export default async function ActsPage() {
  const acts = await getActs()
  return (
    <div className="pt-12">
      <h1 className="statute text-[2.6rem] font-medium tracking-[-0.015em]">Acts</h1>
      <p className="mt-2 max-w-[62ch] text-ink-2">
        The Acts Hakiki holds, with every version the Internet Archive kept. Section numbers stay the same across
        versions, so a court ruling follows its section through each revision.
      </p>
      <div className="mt-8">
        <Shelf acts={acts} />
      </div>
      <ul className="mt-10 divide-y divide-rule border-y border-rule">
        {acts.map((a) => (
          <li key={a.act_id}>
            <Link href={actHref(a.act_id)} className="flex flex-wrap items-baseline gap-x-6 gap-y-1 py-4 hover:bg-panel/60">
              <span className="statute min-w-[16rem] text-xl">{a.title}</span>
              <span className="text-ink-2">{capLabel(a)}</span>
              <span className="ml-auto text-sm text-ink-2">
                {a.versions.length === 1 ? '1 version' : `${a.versions.length} versions`}, latest {fmtDate(a.versions.at(-1)!)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
