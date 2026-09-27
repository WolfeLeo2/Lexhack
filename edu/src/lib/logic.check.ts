// Runnable self-check: `pnpm check` (node strips the types). Fails loudly if the TS rules drift from the Python ones
// (the exported statuses came from api/status_ke.py) or if the checker stops catching the demo filings' problems.
import assert from 'node:assert/strict'
import filings from '../content/filings.json' with { type: 'json' }
import judgments from '../data/judgments.json' with { type: 'json' }
import provisions from '../data/provisions.json' with { type: 'json' }
import { check, diffWords } from './checker.ts'
import { resolve } from './status.ts'
import type { Judgment, ProvisionStatus } from './types.ts'

const P = provisions as unknown as ProvisionStatus[]
const J = judgments as Judgment[]

for (const p of P) {
  const leads = p.with_leads ?? p   // older exports have no leads view
  assert.equal(resolve(leads.history).status, leads.status, `status with leads of s.${p.provision.number}`)
  assert.ok(p.history.every((e) => e.verified), 'default view is verified only')
  const r = resolve(p.history)
  assert.equal(r.status, p.status, `status of s.${p.provision.number}`)
  assert.deepEqual(
    r.history.map((e) => [e.event_id, e.state, e.superseded_by]),
    p.history.map((e) => [e.event_id, e.state, e.superseded_by]),
  )
}

const run = (id: string) => check(filings.find((f) => f.id === id)!.text, P, J)

const a = run('sentence')
const s204 = a.find((f) => f.kind === 'section' && f.number === '204')
assert.equal(s204?.kind === 'section' && s204.result?.status, 'limited by a court')
const mur = a.find((f) => f.kind === 'case' && f.name.includes('Muruatetu'))
assert.equal(mur?.kind === 'case' && mur.name, 'Francis Karioko Muruatetu & another v Republic')
assert.ok(mur?.kind === 'case' && mur.judgment?.judgment_id === 'ke/judgment/kesc/2017/2', 'Muruatetu found')
assert.ok(mur?.kind === 'case' && mur.quote && !mur.quote.verbatim && mur.quote.closest, 'misquote caught')
const kamName = a.find((f) => f.kind === 'case' && f.name.includes('Kamau'))
assert.equal(kamName?.kind === 'case' && kamName.name, 'Wanjiru Kamau v Republic')
const kam = a.find((f) => f.kind === 'case' && f.name.includes('Kamau'))
assert.ok(kam?.kind === 'case' && kam.judgment === null, 'unknown case not matched')

const b = run('speech')
assert.deepEqual(
  b.filter((f) => f.kind === 'section').map((f) => f.kind === 'section' && f.result?.status),
  ['limited by a court', 'declared unconstitutional', 'declared unconstitutional', 'limited by a court'],  // the last is inside the Okuta quote
)
assert.ok(b.some((f) => f.kind === 'case' && f.quote?.verbatim), 'Okuta quote verbatim')

const c = run('defilement')
const cases = c.filter((f) => f.kind === 'case')
assert.equal(cases.length, 2)
for (const f of cases) {
  assert.ok(f.kind === 'case' && f.judgment && f.quote?.verbatim, `${f.name} found and quoted verbatim`)
  assert.ok(f.kind === 'case' && f.rulings.every((r) => r.event.state === 'reversed on appeal'), `${f.name} reversed`)
}

const d = diffWords('the cat sat', 'yesterday the black cat sat down')
assert.deepEqual(d.map((t) => t.kind), ['same', 'missing', 'same', 'same'])

console.log(`ok: ${P.length} sections match the Python rules; 3 demo filings check out`)
