import type { Metadata } from 'next'
import { FilingUnderGlass } from '@/components/illustrations'
import { Checker } from './Checker'

export const metadata: Metadata = { title: 'Check a filing' }

export default function CheckPage() {
  return (
    <>
      <section className="grid grid-cols-1 items-center gap-x-14 gap-y-6 pt-12 pb-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)] lg:pt-16">
        <div>
          <h1 className="statute text-[2.4rem] leading-[1.08] font-medium tracking-[-0.02em] sm:text-[3.2rem]">Check the citations in a filing</h1>
          <p className="mt-5 max-w-[56ch] text-lg text-ink-2">
            Paste a submission, pleading or judgment. Hakiki finds every case and section it cites, then reports what the sources say: whether we hold the case, whether the
            quoted words are really in it, and what the courts have done to each section.
          </p>
          <p className="mt-3 text-[0.95rem] text-ink-2">Your text is checked and thrown away. Nothing is stored.</p>
        </div>
        <FilingUnderGlass className="mx-auto hidden w-full max-w-[22rem] lg:block" />
      </section>
      <Checker />
    </>
  )
}
