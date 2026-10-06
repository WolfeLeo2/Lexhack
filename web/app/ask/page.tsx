import type { Metadata } from 'next'
import { QuestionToTheBook } from '@/components/illustrations'
import { Ask } from './Ask'

export const metadata: Metadata = { title: 'Ask Hakiki' }

export default function AskPage() {
  return (
    <>
      <section className="grid grid-cols-1 items-center gap-x-14 gap-y-6 pt-12 pb-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)] lg:pt-16">
        <div>
          <h1 className="statute text-[2.4rem] leading-[1.08] font-medium tracking-[-0.02em] sm:text-[3.2rem]">Ask Hakiki</h1>
          <p className="mt-5 max-w-[56ch] text-lg text-ink-2">
            Ask about a section of a Kenyan Act or a court ruling in plain words. Hakiki looks it up in its own records and
            answers with the section’s status and the court’s words, linked to each judgment.
          </p>
          <p className="mt-4 max-w-[60ch] border-l-2 border-seal/60 pl-3 text-[0.95rem] text-ink-2">
            Hakiki reports what published sources say. It is not legal advice. Answers are written by an AI model from
            Hakiki’s records; the court’s words are quoted from the database, never by the model.
          </p>
        </div>
        <QuestionToTheBook className="mx-auto hidden w-full max-w-[20rem] lg:block" />
      </section>
      <Ask />
    </>
  )
}
