import Link from 'next/link'
import { BlankPage } from '@/components/illustrations'

export default function NotFound() {
  return (
    <div className="flex max-w-[62ch] items-center gap-8 pt-16">
      <BlankPage className="h-32 w-28 shrink-0" />
      <div>
        <h1 className="statute text-[2.2rem] font-medium">No such section or Act</h1>
        <p className="mt-3 text-ink-2">
          The link may be from an Act we don’t hold yet. Browse the <Link href="/acts" className="link">Acts we hold</Link>, or
          search for the section by its subject.
        </p>
      </div>
    </div>
  )
}
