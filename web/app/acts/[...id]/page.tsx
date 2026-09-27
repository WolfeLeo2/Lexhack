import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { SectionList } from '@/components/SectionList'
import { VersionRail } from '@/components/VersionRail'
import { getActs, getSections } from '@/lib/api'
import { capLabel } from '@/lib/format'

type Props = PageProps<'/acts/[...id]'>

const actId = async (props: Props) => (await props.params).id.map(decodeURIComponent).join('/')

export async function generateMetadata(props: Props): Promise<Metadata> {
  const id = await actId(props)
  const act = (await getActs()).find((a) => a.act_id === id)
  return act ? { title: act.title } : {}
}

export default async function ActPage(props: Props) {
  const id = await actId(props)
  const [acts, sections] = await Promise.all([getActs(), getSections(id)])
  const act = acts.find((a) => a.act_id === id)
  if (!act || !sections) notFound()

  return (
    <div className="pt-8">
      <nav aria-label="Breadcrumb" className="text-[0.95rem] text-ink-2">
        <Link href="/acts" className="hover:text-ink">
          Acts
        </Link>
        <span aria-hidden> / </span>
        <span aria-current="page">{act.title}</span>
      </nav>
      <h1 className="statute mt-6 text-[2.6rem] leading-[1.1] font-medium tracking-[-0.015em] sm:text-[3.2rem]">{act.title}</h1>
      <p className="statute mt-1 text-lg text-ink-2">{capLabel(act)}</p>

      <div className="mt-8">
        <VersionRail versions={act.versions} />
      </div>

      <div className="mt-10">
        <SectionList sections={sections} />
      </div>
    </div>
  )
}
