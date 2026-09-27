import type { Metadata } from 'next'
import Link from 'next/link'
import { getStats } from '@/lib/api'
import { plural } from '@/lib/format'

export const metadata: Metadata = { title: 'About and how to use it' }

// The labels api/status_ke.py can return, in plain words.
const STATUSES: [string, string][] = [
  ['Declared unconstitutional', 'A court struck down the whole section. It is still printed in the Act, but it has no force.'],
  [
    'Limited by a court',
    'A court struck down or narrowed part of the section, usually “to the extent that” it goes too far. The rest still applies. Read the highlighted words to see which part.',
  ],
  ['In force; its validity has been tested in court', 'Someone challenged the section and a court upheld it.'],
  ['In force; earlier court limits were reversed', 'A court limited the section, and a higher court later reversed or overruled that ruling.'],
  ['In force; interpreted by a court', 'A court has said how the section must be read, without limiting or upholding it.'],
  [
    'In force; no recorded court rulings',
    'None of the rulings checked so far limits, upholds or strikes down the section. Most sections are like this: courts apply them every day without ruling on them.',
  ],
  ['Repealed', 'Parliament removed the whole section, according to the reviser’s note in Kenya Law’s own text.'],
]

export default async function AboutPage() {
  const s = await getStats()
  return (
    <div className="max-w-[70ch] pt-12">
      <h1 className="statute text-[2.8rem] leading-[1.1] font-medium tracking-[-0.015em]">About Hakiki</h1>
      <p className="mt-4 text-lg text-ink-2">
        <i>Hakiki</i> is Swahili for “verify”. It tells you whether a section of a Kenyan Act is still good law: in
        force, limited, upheld, or struck down by a court, with the court’s own words and a link to the judgment.
      </p>

      <h2 className="statute mt-14 text-[1.9rem] font-medium">Why it exists</h2>
      <div className="mt-3 space-y-4">
        <p>
          Kenya Law publishes the official consolidated text of every Act. That text records what Parliament changed, but
          not what the courts decided. Section 204 of the Penal Code still reads “Any person convicted of murder shall be
          sentenced to death”, years after the Supreme Court in <i>Muruatetu</i> (2017) held the mandatory death sentence
          unconstitutional. Section 194, criminal libel, carries no note of <i>Okuta</i> (2017).
        </p>
        <p>
          So anyone who reads the published text, whether a lawyer, a student or an AI tool, can cite a section a court
          has already cut down. Hakiki joins the two: the statute, and what the courts have done to it.
        </p>
      </div>

      <h2 className="statute mt-14 text-[1.9rem] font-medium">How to use it</h2>
      <ol className="mt-4 list-decimal space-y-4 pl-6 marker:text-ink-2">
        <li>
          <strong className="font-medium">Find the section.</strong> Search by subject or by words from the text (“libel”,
          “punishment of murder”), or <Link href="/acts" className="link">open an Act</Link> and type the section number.
          Search matches the statute’s own wording, so use the legal term: “defilement”, not “sex with a child”.
        </li>
        <li>
          <strong className="font-medium">Read the stamp.</strong> Next to the text is the section’s status, in words. It is
          never a simple yes or no, because courts often strike down only part of a section. The meanings are below.
        </li>
        <li>
          <strong className="font-medium">Read the court’s words.</strong> Under the stamp are the rulings that produce the
          status, quoted exactly. Highlighted words are the part that limits the section, such as “to the extent that…”.
          Each ruling names the case, the court, the date and the paragraph, and links to the judgment on Kenya Law.
        </li>
        <li>
          <strong className="font-medium">Follow the history.</strong> The chart shows every ruling by court and year. An
          arrow runs from a ruling to the earlier one it reversed on appeal (solid) or displaced (dashed: a later court of
          equal or higher rank decided the other way). Crossed-out marks no longer count.
        </li>
        <li>
          <strong className="font-medium">Treat leads as leads.</strong> “Show unverified leads” adds rulings our pipeline
          found in judgments that no reviewer has checked yet. They are drawn with dashed lines and never change the
          status. Read the judgment before relying on one.
        </li>
        <li>
          <strong className="font-medium">See how courts use it.</strong> At the bottom is every judgment we hold that cites
          the section, highest court first.
        </li>
      </ol>

      <h2 className="statute mt-14 text-[1.9rem] font-medium">What the statuses mean</h2>
      <dl className="mt-4 divide-y divide-rule border-y border-rule">
        {STATUSES.map(([label, meaning]) => (
          <div key={label} className="grid gap-x-6 gap-y-1 py-3 sm:grid-cols-[16rem_minmax(0,1fr)]">
            <dt className="statute text-lg text-seal">{label}</dt>
            <dd className="text-ink-2">{meaning}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-[0.95rem] text-ink-2">
        “In force” means no ruling we hold says otherwise. Parliament’s amendments and repeals come from the reviser’s notes in
        Kenya Law’s text, which give only the year; the text shown is the latest version we hold.
      </p>

      <h2 className="statute mt-14 text-[1.9rem] font-medium">Where the information comes from</h2>
      <ul className="mt-4 list-disc space-y-3 pl-6 marker:text-ink-2">
        <li>
          <strong className="font-medium">Statutes:</strong> {plural(s.acts, 'Act')} ({plural(s.sections, 'section')}) from
          Kenya Law, every version the Internet Archive kept.
        </li>
        <li>
          <strong className="font-medium">Judgments:</strong> {plural(s.judgments, 'judgment')} of the Supreme Court, Court
          of Appeal and High Court, also from the Internet Archive. That is about a tenth of all Kenyan judgments, so a
          missing ruling is not proof that none exists.
        </li>
        <li>
          <strong className="font-medium">Checked rulings:</strong> {plural(s.verified_events, 'ruling')} on{' '}
          {plural(s.verified_sections, 'section')}, each read against the full judgment, with the operative words
          copied exactly. Each is labelled with who checked it: {plural(s.person_events, 'ruling')} by a person,{' '}
          {plural(s.agent_events, 'ruling')} by an AI reviewer. The AI reviewer reads the judgment itself and is held to
          a benchmark: on 111 events reviewed blind by two earlier reviewers, every ruling it accepted was right, and it
          kept 59 of 63 real ones.
        </li>
        <li>
          <strong className="font-medium">Leads:</strong> {plural(s.leads, 'possible ruling')} on{' '}
          {plural(s.lead_sections, 'section')}, found by a language model reading the judgments and then checked by a
          second model. In a blind review about four in five were right. They stay marked as unverified until a
          reviewer checks them against the judgment.
        </li>
        <li>
          <strong className="font-medium">Citations:</strong> every “section N of the … Act” in the judgments, linked to the
          section it names. On judgments held out for testing this was 98% accurate. {plural(s.cited_sections, 'section')}{' '}
          are cited at least once.
        </li>
      </ul>

      <h2 className="statute mt-14 text-[1.9rem] font-medium">What it is not</h2>
      <p className="mt-3">
        Hakiki reports what published sources say. It is not legal advice, and it does not tell you whether a case
        supports your argument. Always read the judgment itself.
      </p>
      <p className="mt-4 text-ink-2">Hakiki was built by a team of two for LexHack 2026, a student hackathon on AI, law and civic tech.</p>
    </div>
  )
}
