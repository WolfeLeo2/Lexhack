import type { Metadata } from 'next'
import { Checker } from './Checker'

export const metadata: Metadata = { title: 'Check a filing' }

export default function CheckPage() {
  return (
    <div className="pt-10">
      <h1 className="statute text-3xl">Check a filing</h1>
      <p className="mt-3 max-w-[68ch] text-ink-2">
        Paste a submission, pleading or judgment. Hakiki finds each case and section it cites and reports what the sources say: whether we hold the case, whether quoted
        words appear in it, and what courts have done to each section. Your text is not stored.
      </p>
      <Checker />
    </div>
  )
}
